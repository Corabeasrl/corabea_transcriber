import logging

import requests

from .config import Settings

logger = logging.getLogger("summarizer")


class SummarizerError(Exception):
    pass


class Summarizer:
    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def enabled(self) -> bool:
        return self._s.llm_enabled

    def summarize(self, transcript: str) -> str:
        text = (transcript or "").strip()
        if not text:
            raise SummarizerError("empty transcript")

        url = f"{self._s.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._s.llm_model,
            "messages": [
                {"role": "system", "content": self._s.llm_system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": self._s.llm_max_tokens,
            "stream": False,
        }
        logger.info("requesting summary from %s (model=%s)", url, self._s.llm_model)
        resp = requests.post(url, json=payload, timeout=self._s.llm_timeout)
        if resp.status_code != 200:
            raise SummarizerError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            summary = resp.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as e:
            raise SummarizerError(f"unexpected LLM response: {e}") from e
        if not summary:
            raise SummarizerError("LLM returned an empty summary")
        return summary
