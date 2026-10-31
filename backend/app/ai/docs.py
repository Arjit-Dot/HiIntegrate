"""Read an API documentation page for config authoring (AI mode): a URL in, plain text out.

The server fetches a URL a person typed, so this is built to be safe to point at anything:
https only, no credentials in the URL, every hop (including redirects) must resolve to a public address,
a small size cap, a short timeout, and only text-like content. Nothing from the page is executed.
Known limit: the address is checked, then httpx connects by name, so a DNS answer that changes between the
two could slip through. Acceptable for a local, single-user tool; pin the resolved IP before exposing this.
"""

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 1_500_000
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

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        if tag == "pre":
            self.pre += 1
        if tag in _BREAK and not self.skip:
            self.out.append("\n")
        if tag in {"h1", "h2", "h3"} and not self.skip:
            self.out.append("## ")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        if tag == "pre" and self.pre:
            self.pre -= 1
        if tag in _BREAK and not self.skip:
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def to_text(body: str, content_type: str) -> str:
    if "html" in content_type or "xhtml" in content_type or re.match(r"\s*(<!doctype html|<html)", body, re.IGNORECASE):
        parser = _Text()
        parser.feed(body)
        text = "".join(parser.out)
    else:
        text = body  # JSON, YAML (an OpenAPI file is ideal) and plain text are already readable
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_docs(url: str, *, client: httpx.Client | None = None, check=check_url) -> dict:
    """Returns {url, text, chars, truncated}. Raises DocsError with a message for the person."""
    current = check(url)
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": "HiIntegrate-docs-reader/1.0", "Accept": "text/html,application/json,text/plain,*/*;q=0.5"})
    try:
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
                            raise DocsError("the page is larger than 1.5 MB")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    break
            except httpx.HTTPError as exc:
                raise DocsError(f"could not fetch the page ({type(exc).__name__})") from None
        else:
            raise DocsError("the page redirected too many times")
    finally:
        if own:
            client.close()
    text = to_text(body, content_type)
    if len(text) < MIN_CHARS:
        raise DocsError("the page has almost no readable text (it may need JavaScript). Paste the text, a curl example or a sample response instead")
    return {"url": current, "text": text[:MAX_CHARS], "chars": len(text), "truncated": len(text) > MAX_CHARS}
