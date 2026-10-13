"""Optional local script generation via Ollama; no hosted AI key required."""
from __future__ import annotations
import requests

def generate_script(topic: str, language: str = "az", duration_seconds: int = 50,
                    model: str = "qwen2.5:3b", base_url: str = "http://127.0.0.1:11434",
                    timeout: int = 240) -> str:
    names = {"az": "Azerbaijani", "tr": "Turkish", "en": "English"}
    language_name = names.get(language, "Azerbaijani")
    words = max(45, round(duration_seconds * 2.05))
    prompt = (
        f"Write a natural spoken YouTube narration in {language_name}.\n"
        f"Topic: {topic}\nTarget duration: {duration_seconds} seconds, about {words} words.\n"
        "Use short sentences and an engaging opening. Do not invent statistics or sources. "
        "Return only narration text, no title, markdown, or stage directions."
    )
    response = requests.post(
        base_url.rstrip("/") + "/api/chat",
        json={"model": model, "stream": False,
              "messages": [{"role": "system", "content": "You write accurate, natural video narration."},
                           {"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    response.raise_for_status()
    text = (response.json().get("message") or {}).get("content", "").strip()
    if len(text.split()) < max(20, round(duration_seconds * 0.7)):
        raise RuntimeError("Ollama returned a very short script; check the model and prompt.")
    return text
