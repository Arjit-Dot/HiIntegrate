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
    def __init__(self, api_key: str, model: str, *, http: httpx.Client | None = None, timeout: float = 60, sleep=time.sleep):
        self._key, self.model, self._http, self._timeout, self._sleep = api_key, model, http, timeout, sleep

    @classmethod
    def from_settings(cls) -> "LLMClient | None":
        """None when LLM_API_KEY is not set: the AI routes then answer 501 and the rest of the product is unaffected."""
        settings = get_settings()
        return cls(settings.llm_api_key, settings.llm_model) if settings.llm_api_key else None

    def generate(self, system: str, user: str, *, json_output: bool = False, temperature: float = 0.2) -> str:
        body: dict = {
            "systemInstruction": {"parts": [{"text": scrub(system)}]},
            "contents": [{"role": "user", "parts": [{"text": scrub(user)}]}],
            "generationConfig": {"temperature": temperature, **({"responseMimeType": "application/json"} if json_output else {})},
        }
        url = f"{BASE_URL}/models/{self.model}:generateContent"
        client = self._http or httpx.Client(timeout=self._timeout)
        try:
            for attempt in range(len(BACKOFF) + 1):
                last = attempt == len(BACKOFF)
                try:
                    response = client.post(url, json=body, headers={"x-goog-api-key": self._key})
                except httpx.HTTPError as exc:
                    if last:
                        raise LLMError(f"the model could not be reached ({type(exc).__name__})") from None
                    self._sleep(BACKOFF[attempt])
                    continue
                if response.status_code in RETRY_STATUS and not last:
                    self._sleep(BACKOFF[attempt])
                    continue
                break
        finally:
            if self._http is None:
                client.close()
        if response.status_code != 200:
            raise LLMError(f"the model answered {response.status_code}: {_reason(response)}")
        text = _text(response)
        log.info("llm call ok model=%s chars=%s", self.model, len(text))
        return text


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
