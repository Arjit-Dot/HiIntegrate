"""The LLM wrapper (D-14): Google Gemini over REST. The key comes from LLM_API_KEY, the model from LLM_MODEL.

The key travels in a header, never in a URL, and nothing is logged but the model name and the outcome.
Every prompt is scrubbed again here (redact.scrub), whatever the caller did.
"""

import logging
import time

import httpx

from app.ai.redact import scrub
from app.core.settings import get_settings

log = logging.getLogger("ai")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF = (2, 5)  # seconds before the 2nd and 3rd try: Gemini answers 503 "high demand" now and then


class LLMError(Exception):
    """The model could not be reached or gave nothing usable."""


class LLMClient:
    def __init__(self, api_key: str, model: str, *, fallback: str | None = None, http: httpx.Client | None = None, timeout: float = 60, sleep=time.sleep):
        self._key, self.model, self.fallback, self._http, self._timeout, self._sleep = api_key, model, fallback, http, timeout, sleep

    @classmethod
    def from_settings(cls) -> "LLMClient | None":
        """None when LLM_API_KEY is not set: the AI routes then answer 501 and the rest of the product is unaffected."""
        settings = get_settings()
        return cls(settings.llm_api_key, settings.llm_model, fallback=settings.llm_fallback_model or None) if settings.llm_api_key else None

    def generate(self, system: str, user: str, *, json_output: bool = False, temperature: float = 0.2) -> str:
        body: dict = {
            "systemInstruction": {"parts": [{"text": scrub(system)}]},
            "contents": [{"role": "user", "parts": [{"text": scrub(user)}]}],
            "generationConfig": {"temperature": temperature, **({"responseMimeType": "application/json"} if json_output else {})},
        }
        client = self._http or httpx.Client(timeout=self._timeout)
        try:
            # The main model first. If it stays overloaded or unreachable, the fallback model gets the same request.
            models = [self.model, *([self.fallback] if self.fallback and self.fallback != self.model else [])]
            for n, model in enumerate(models):
                response, failure = self._post(client, model, body)
                if response is not None and response.status_code == 200:
                    text = _text(response)
                    log.info("llm call ok model=%s chars=%s", model, len(text))
                    return text
                last = n == len(models) - 1
                transient = failure is not None or (response is not None and response.status_code in RETRY_STATUS)
                if last or not transient:
                    raise LLMError(failure or f"the model answered {response.status_code}: {_reason(response)}")
                log.warning("llm model %s is unavailable, trying %s", model, models[n + 1])
        finally:
            if self._http is None:
                client.close()
        raise LLMError("the model could not be reached")  # not reached; keeps the type checker honest

    def _post(self, client: httpx.Client, model: str, body: dict) -> tuple[httpx.Response | None, str | None]:
        """Up to three tries with a pause between. Returns (response, None), or (None, why) if it could not be reached."""
        url = f"{BASE_URL}/models/{model}:generateContent"
        response = None
        for attempt in range(len(BACKOFF) + 1):
            last = attempt == len(BACKOFF)
            try:
                response = client.post(url, json=body, headers={"x-goog-api-key": self._key})
            except httpx.HTTPError as exc:
                if last:
                    return None, f"the model could not be reached ({type(exc).__name__})"
                self._sleep(BACKOFF[attempt])
                continue
            if response.status_code in RETRY_STATUS and not last:
                self._sleep(BACKOFF[attempt])
                continue
            break
        return response, None


def _reason(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return "no detail"


def _text(response: httpx.Response) -> str:
    try:
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("the model returned no answer (it may have been blocked)") from None
    if not text.strip():
        raise LLMError("the model returned an empty answer")
    return text
