from __future__ import annotations

import os

import httpx

_GROQ_MODEL = "llama-3.1-8b-instant"
_OLLAMA_BASE = "http://localhost:11434"


async def list_ollama_models() -> list[str]:
    """Return all available Ollama model names, or empty list if unreachable."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{_OLLAMA_BASE}/api/tags")
            if r.status_code != 200:
                return []
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


async def summarize_article(title: str, text: str, ollama_model: str = "llama3.2") -> str | None:
    prompt = (
        f"Summarize this news article in one concise paragraph. "
        f"Output only the summary text, no preamble or introduction.\n\n"
        f"Title: {title}\n\n{text[:4000]}"
    )
    result = await _try_ollama(prompt, ollama_model)
    if result is not None:
        return result
    return await _try_groq(prompt)


async def _try_ollama(prompt: str, model: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{_OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
    except Exception:
        return None


async def _try_groq(prompt: str) -> str | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": _GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
