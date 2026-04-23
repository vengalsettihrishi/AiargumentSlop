"""
llm_client.py
─────────────
Unified LLM client that wraps OpenAI, Anthropic, and Groq.
Provider is selected by PRIMARY_LLM_PROVIDER in .env.
Implements automatic failover: primary → anthropic → groq.
"""

from __future__ import annotations
import logging
from typing import Optional

from config import settings

log = logging.getLogger(__name__)


# ── Provider implementations ──────────────────────────────────────────────────

def _call_openai(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    model: Optional[str] = None,
) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=model or settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    model: Optional[str] = None,
) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model or settings.ANTHROPIC_MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.content[0].text.strip()


def _call_groq(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    model: Optional[str] = None,
) -> str:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model=model or settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Dispatch table ────────────────────────────────────────────────────────────

_PROVIDERS = {
    "openai":    _call_openai,
    "anthropic": _call_anthropic,
    "groq":      _call_groq,
}


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[str, str]:
    """
    Call the configured LLM provider.

    Args:
        provider:  Force a specific provider ("openai" | "anthropic" | "groq").
                   Falls back through the chain if this provider fails.
        model:     Override the model name within the chosen provider.
                   Useful for Sprint 2 where Skeptic-A must be GPT-4o
                   and Skeptic-B must be Claude 3.5 regardless of global config.

    Returns:
        (response_text, provider_name_used)

    Raises:
        RuntimeError if all configured providers fail.
    """
    primary = provider or settings.PRIMARY_LLM_PROVIDER
    # Build failover chain: requested provider first, then others
    chain = [primary] + [p for p in ("openai", "anthropic", "groq") if p != primary]

    last_exc: Optional[Exception] = None
    for prov in chain:
        fn = _PROVIDERS.get(prov)
        if fn is None:
            continue
        key_map = {
            "openai":    settings.OPENAI_API_KEY,
            "anthropic": settings.ANTHROPIC_API_KEY,
            "groq":      settings.GROQ_API_KEY,
        }
        if not key_map.get(prov, ""):
            log.debug("Skipping %s — no API key configured.", prov)
            continue
        try:
            log.info("Calling LLM via [%s] (model=%s) …", prov, model or "default")
            text = fn(system_prompt, user_prompt, max_tokens, temperature, model)
            return text, prov
        except Exception as exc:  # noqa: BLE001
            log.warning("Provider [%s] failed: %s — trying next.", prov, exc)
            last_exc = exc

    raise RuntimeError(
        f"All LLM providers failed. Last error: {last_exc}"
    )
