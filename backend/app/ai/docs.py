"""Read an API documentation page for config authoring (AI mode): a URL in, plain text out.

The server fetches a URL a person typed, so this is built to be safe to point at anything:
https only, no credentials in the URL, every hop (including redirects) must resolve to a public address,
a size cap, a short timeout, and only text-like content. Nothing from the page is executed.
Known limit: the address is checked, then httpx connects by name, so a DNS answer that changes between the
two could slip through. Acceptable for a local, single-user tool; pin the resolved IP before exposing this.
"""

import ipaddress
import json
import math
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import yaml

MAX_BYTES = 8_000_000
MAX_CHARS = 50_000  # what the model gets, roughly 12k tokens
MIN_CHARS = 200  # less than this usually means a page that needs JavaScript
MAX_REDIRECTS = 3
TEXT_TYPES = ("text/", "application/json", "application/yaml", "application/x-yaml", "application/xml", "application/xhtml")


class DocsError(Exception):
    """The page cannot be used. The message is safe to show to the person."""


def _public(host: str) -> None:
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise DocsError(f"cannot find the host {host}") from None
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise DocsError(f"{host} is not a public address, so it is not fetched")


def check_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise DocsError("the documentation URL must start with https://")
    if parts.username or parts.password:
        raise DocsError("the URL must not contain a user name or password")
    if parts.port not in (None, 443):
        raise DocsError("only the standard https port is allowed")
    _public(parts.hostname)
    return parts.geturl()


_SKIP = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"})
_BREAK = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "section", "article", "table", "ul", "ol"})


class _Text(HTMLParser):
    """Visible text, keeping code blocks and line breaks, which is where endpoints and examples live."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.links: list[tuple[str, str]] = []  # (href, text), for following to a better page
        self._href: str | None = None
        self._label: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._label = []
        if tag in _SKIP:
            self.skip += 1
        if tag == "pre":
            self.pre += 1
        if tag in _BREAK and not self.skip:
            self.out.append("\n")
        if tag in {"h1", "h2", "h3"} and not self.skip:
            self.out.append("## ")

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._label).split())[:80]))
            self._href = None
        if tag in _SKIP and self.skip:
            self.skip -= 1
        if tag == "pre" and self.pre:
            self.pre -= 1
        if tag in _BREAK and not self.skip:
            self.out.append("\n")

    def handle_data(self, data):
        if self._href is not None:
            self._label.append(data)
        if self.skip:
            return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def page_links(body: str, base: str, limit: int = 150) -> list[dict]:
    """Links on an HTML page that stay on the same site, so the AI can pick a better page to read."""
    parser = _Text()
    parser.feed(body)
    host = urlsplit(base).hostname
    seen, out = set(), []
    for href, label in parser.links:
        url = urljoin(base, href.split("#")[0])
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != host or url in seen or url == base:
            continue
        seen.add(url)
        out.append({"url": url, "text": label})
    return out[:limit]


def to_text(body: str, content_type: str) -> str:
    if "html" in content_type or re.search(r"<(!doctype html|html|body|head)\b", body[:2000], re.IGNORECASE):
        parser = _Text()
        parser.feed(body)
        text = "".join(parser.out)
    else:
        text = body  # JSON, YAML (an OpenAPI file is ideal) and plain text are already readable
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------- big pages: keep what matters

_WEIGHTS = {"user": 3, "member": 2, "device": 3, "host": 2, "endpoint": 2, "alert": 3, "finding": 2, "vulnerab": 2, "list": 2, "search": 2,
            "paginat": 2, "authenticat": 3, "api key": 2, "base url": 3, "startat": 2, "offset": 1, "cursor": 1, "get /": 2, "token": 1}
HEAD_CHARS = 5000  # the start of a page usually says what the API is, its base URL and how to log in


def _blocks(text: str, size: int = 1800) -> list[str]:
    out = []
    for part in re.split(r"\n\s*\n", text):
        while len(part) > size:
            cut = part.rfind("\n", 0, size)
            cut = cut if cut > size // 2 else size
            out.append(part[:cut])
            part = part[cut:]
        if part.strip():
            out.append(part)
    return out


def select_relevant(text: str, limit: int = MAX_CHARS) -> str:
    """Fit a long page into `limit` characters: always the start, then the parts that talk about users, devices, alerts,
    endpoints, paging and login, in their original order. Short pages are returned unchanged."""
    if len(text) <= limit:
        return text
    blocks = _blocks(text)
    keep, used = set(), 0
    for i, b in enumerate(blocks):
        if used + len(b) > min(HEAD_CHARS, limit):
            break
        keep.add(i)
        used += len(b) + 2

    def score(b: str) -> float:
        low = b.lower()
        return sum(low.count(k) * w for k, w in _WEIGHTS.items()) / math.sqrt(len(b) + 100)

    for i in sorted((i for i in range(len(blocks)) if i not in keep), key=lambda i: -score(blocks[i])):
        if used + len(blocks[i]) > limit:
            continue
        if score(blocks[i]) <= 0:
            break
        keep.add(i)
        used += len(blocks[i]) + 2
    return "\n\n".join(blocks[i] for i in sorted(keep))


# ---------------------------------------------------------------- OpenAPI files: a short list of endpoints

def _deref(spec: dict, node):
    for _ in range(5):
        if isinstance(node, dict) and "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/"):
            cur = spec
            for part in node["$ref"][2:].split("/"):
                cur = cur.get(part, {}) if isinstance(cur, dict) else {}
            node = cur
        else:
            break
    return node


def _shape(spec: dict, schema, depth: int = 2) -> str:
    schema = _deref(spec, schema)
    if not isinstance(schema, dict):
        return "any"
    if schema.get("type") == "array" or "items" in schema:
        return f"[{_shape(spec, schema.get('items'), depth)}]"
    props = schema.get("properties")
    if props:
        if depth <= 0:
            return "{...}"
        return "{" + ", ".join(k if depth == 1 else f"{k}: {_shape(spec, v, depth - 1)}" for k, v in list(props.items())[:30]) + "}"
    return str(schema.get("type") or "any")


def openapi_to_text(spec: dict) -> str | None:
    """An OpenAPI/Swagger document as one line per endpoint (method, path, summary, parameters, the 200 response's fields)."""
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        return None
    info = spec.get("info") or {}
    lines = [f"API: {info.get('title', '')}. {str(info.get('description', ''))[:400]}".strip()]
    servers = [x.get("url") for x in spec.get("servers") or [] if isinstance(x, dict) and x.get("url")]
    if servers:
        lines.append("Base URL: " + ", ".join(servers[:3]))
    elif spec.get("host"):
        lines.append(f"Base URL: https://{spec['host']}{spec.get('basePath', '')}")
    schemes = (spec.get("components") or {}).get("securitySchemes") or spec.get("securityDefinitions") or {}
    for name, sch in list(schemes.items())[:6]:
        sch = _deref(spec, sch)
        lines.append(f"Auth scheme {name}: " + " ".join(str(sch.get(k)) for k in ("type", "scheme", "in", "name") if sch.get(k)))
    lines.append("")
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        for method in ("get", "post"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = [_deref(spec, p) for p in (op.get("parameters") or []) + (item.get("parameters") or [])]
            plist = ", ".join(f"{p.get('name')}({p.get('in')}{', required' if p.get('required') else ''})" for p in params if isinstance(p, dict))
            ok = _deref(spec, (op.get("responses") or {}).get("200") or {})
            content = (ok.get("content") or {}).get("application/json") or {}
            body = content.get("schema") or ok.get("schema")
            summary = op.get("summary") or str(op.get("description", ""))[:150]
            lines.append(f"{method.upper()} {path} | {summary} | tags: {', '.join(op.get('tags') or [])} | params: {plist or 'none'}"
                         + (f" | 200 returns: {_shape(spec, body)}" if body else ""))
    return "\n".join(lines)


def _spec_text(body: str, content_type: str) -> str | None:
    head = body[:200].lstrip()
    try:
        if "json" in content_type or head.startswith("{"):
            return openapi_to_text(json.loads(body))
        if "yaml" in content_type or head.startswith(("openapi:", "swagger:")):
            return openapi_to_text(yaml.safe_load(body))
    except (ValueError, yaml.YAMLError, RecursionError):
        return None
    return None


def _get(client: httpx.Client, url: str, check) -> tuple[str, str, str]:
    """One safe GET: every hop must be public (D-14), text only, size capped. Returns (final url, content type, body)."""
    current = check(url)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise DocsError("the page redirected nowhere")
                    current = check(urljoin(current, location))  # every hop must be public too
                    continue
                if response.status_code != 200:
                    raise DocsError(f"the page answered {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type and not content_type.startswith(TEXT_TYPES):
                    raise DocsError(f"the page is {content_type}, not text. Use an HTML page or an OpenAPI file")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise DocsError("the page is larger than 8 MB")
                    chunks.append(chunk)
                return current, content_type, b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise DocsError(f"could not fetch the page ({type(exc).__name__})") from None
    raise DocsError("the page redirected too many times")


def _page(url: str, text: str, links=()) -> dict:
    return {"url": url, "text": select_relevant(text), "chars": len(text), "truncated": len(text) > MAX_CHARS, "links": list(links)}


# ---------------------------------------------------------------- pages that need JavaScript: find what they load

# Most documentation sites that draw themselves with JavaScript (Swagger UI, Redoc, Stoplight, ReadMe) just load an OpenAPI file, so
# the file is found instead: named in the page, at a usual address, or in the service's public repository. Failing that, the site's
# own indexes (llms.txt, sitemap.xml) give links the AI can follow. Every address goes through the same public-only checks.
SPEC_PATHS = ("/openapi.json", "/openapi.yaml", "/openapi.yml", "/swagger.json", "/swagger.yaml", "/swagger/v1/swagger.json", "/v3/api-docs",
              "/api-docs", "/api/openapi.json", "/docs/openapi.json", "/.well-known/openapi.json")
REPO_SPEC_FILES = ("openapi.yaml", "openapi.json", "swagger.json", "openapi/openapi.yaml")
REPO_NAME = re.compile(r"openapi|swagger|api-?spec|api-?description|rest-?api", re.IGNORECASE)
DOC_WORDS = re.compile(r"api|reference|rest|endpoint|swagger|openapi|developer", re.IGNORECASE)
MAX_DISCOVERY_FETCHES = 16
MAX_SITEMAP_LINKS = 40
_SPEC_URL = (
    re.compile(r"""spec-?url\s*=\s*["']([^"']+)["']""", re.IGNORECASE),                           # <redoc spec-url=…>, <rapi-doc spec-url=…>
    re.compile(r"""data-url\s*=\s*["']([^"']+\.(?:json|ya?ml)[^"']*)["']""", re.IGNORECASE),
    re.compile(r"""\burl\s*:\s*["']([^"']+\.(?:json|ya?ml)[^"']*)["']"""),                       # SwaggerUIBundle({ url: "…" })
    re.compile(r"""["']url["']\s*:\s*["']([^"']+\.(?:json|ya?ml)[^"']*)["']"""),
    re.compile(r"""(?:href|src)\s*=\s*["']([^"']*(?:openapi|swagger)[^"']*\.(?:json|ya?ml)[^"']*)["']""", re.IGNORECASE),
)
_NEEDS_JS = re.compile(r"""enable javascript|requires? javascript|javascript is (?:required|disabled)|<noscript|<redoc\b|swagger-ui|"""
                       r"""<div[^>]+id=["']?(?:root|app|__next|__nuxt)["']?[ >/]""", re.IGNORECASE)
_REPO = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)", re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_LOC = re.compile(r"<loc>\s*(https://[^<\s]+)\s*</loc>", re.IGNORECASE)


def looks_script_drawn(body: str, text: str) -> bool:
    """A page with little text and the marks of a page that draws itself in the browser."""
    return len(text) < 1500 and bool(_NEEDS_JS.search(body))


def spec_urls_in(body: str, base: str) -> list[str]:
    """Addresses of an API description file named in the page's own source."""
    found: list[str] = []
    for pattern in _SPEC_URL:
        for match in pattern.findall(body):
            url = urljoin(base, match.strip())
            if url.startswith("https://") and url not in found:
                found.append(url)
    return found[:5]


def repo_spec_urls(body: str) -> list[str]:
    """Raw addresses of an OpenAPI file in a public repository the page links to, when the repository is named like an API spec."""
    repos = []
    for owner, name in _REPO.findall(body):
        name = name.removesuffix(".git")
        if REPO_NAME.search(name) and (owner, name) not in repos:
            repos.append((owner, name))
    return [f"https://raw.githubusercontent.com/{o}/{n}/HEAD/{f}" for o, n in repos[:2] for f in REPO_SPEC_FILES]


def discover(client: httpx.Client, check, page_url: str, body: str) -> dict | None:
    """Look for the API description a script-drawn page loads. Returns a page in the same shape as fetch_docs, or None."""
    origin = "https://" + (urlsplit(page_url).hostname or "")
    budget = [MAX_DISCOVERY_FETCHES]

    def quiet(url: str) -> tuple[str, str, str] | None:
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        try:
            return _get(client, url, check)
        except DocsError:
            return None

    candidates = [*spec_urls_in(body, page_url), *(origin + p for p in SPEC_PATHS), *repo_spec_urls(body)]
    for url in dict.fromkeys(candidates):
        got = quiet(url)
        spec = _spec_text(got[2], got[1]) if got else None
        if spec:
            return _page(got[0], spec)
    for name in ("/llms-full.txt", "/llms.txt"):  # a site's own text index for language models
        got = quiet(origin + name)
        if got and len(got[2].strip()) >= MIN_CHARS and "html" not in got[1]:
            host = urlsplit(got[0]).hostname
            links = [{"url": u, "text": t} for t, u in _MD_LINK.findall(got[2]) if urlsplit(u).hostname == host]
            return _page(got[0], got[2].strip(), links[:150])
    got = quiet(origin + "/sitemap.xml")
    if got:
        host = urlsplit(got[0]).hostname
        urls = [u for u in dict.fromkeys(_LOC.findall(got[2])) if urlsplit(u).hostname == host and not u.endswith(".xml") and DOC_WORDS.search(urlsplit(u).path)]
        if urls:
            urls = urls[:MAX_SITEMAP_LINKS]
            return _page(got[0], "Pages on this site that look like API documentation:\n" + "\n".join(urls), [{"url": u, "text": urlsplit(u).path} for u in urls])
    return None


def fetch_docs(url: str, *, client: httpx.Client | None = None, check=check_url) -> dict:
    """Returns {url, text, chars, truncated, links}. Raises DocsError with a message for the person.
    A page that draws itself with JavaScript has almost no text, so the API description it loads is looked for instead (see `discover`):
    the returned `url` is then that file, which is the page that was really read."""
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": "HiIntegrate-docs-reader/1.0", "Accept": "text/html,application/json,text/plain,*/*;q=0.5"})
    try:
        current, content_type, body = _get(client, url, check)
        is_html = "html" in content_type or bool(re.search(r"<(!doctype html|html|body|head)\b", body[:2000], re.IGNORECASE))
        links = page_links(body, current) if is_html else []
        text = _spec_text(body, content_type) or to_text(body, content_type)
        if is_html and (len(text) < MIN_CHARS or looks_script_drawn(body, text)):
            found = discover(client, check, current, body)
            if found:
                return found
        if len(text) < MIN_CHARS:
            raise DocsError("the page has almost no readable text (it needs JavaScript to show its content, and no API description file was found behind it). "
                            "Copy the text from your browser and paste it, or paste a curl example or a sample response instead")
        return _page(current, text, links)
    finally:
        if own:
            client.close()


def prepare_text(text: str) -> str:
    """Pasted or attached text for the model: HTML is turned into plain text, and the length is capped like a fetched page."""
    return select_relevant(to_text(text, ""))
