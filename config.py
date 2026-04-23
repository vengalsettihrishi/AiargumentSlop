"""
config.py
─────────
Loads all environment variables from .env and exposes a single
`settings` object used across every module in the system.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from the project root ──────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env")


# ── Helper functions (SAFE parsing) ──────────────────────────
def get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default


def get_float(key: str, default: float) -> float:
    value = os.getenv(key, str(default))
    try:
        return float(value)
    except ValueError:
        # fix cases like "0.2D"
        cleaned = ''.join(c for c in value if c.isdigit() or c == '.')
        try:
            return float(cleaned)
        except:
            return default


def get_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() == "true"


class Settings:
    # ── LLM providers ──────────────────────────────────────
    OPENAI_API_KEY: str        = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str          = os.getenv("OPENAI_MODEL", "gpt-4o")

    ANTHROPIC_API_KEY: str     = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str       = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    GROQ_API_KEY: str          = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str            = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    PRIMARY_LLM_PROVIDER: str  = os.getenv("PRIMARY_LLM_PROVIDER", "openai")

    # ── Retrieval ───────────────────────────────────────────
    TAVILY_API_KEY: str        = os.getenv("TAVILY_API_KEY", "")
    SERPER_API_KEY: str        = os.getenv("SERPER_API_KEY", "")
    YOU_API_KEY: str           = os.getenv("YOU_API_KEY", "")

    # ── Vector store ────────────────────────────────────────
    PINECONE_API_KEY: str      = os.getenv("PINECONE_API_KEY", "")
    PINECONE_ENVIRONMENT: str  = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
    PINECONE_INDEX_NAME: str   = os.getenv("PINECONE_INDEX_NAME", "debate-claims")

    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # ── Sprint runtime ──────────────────────────────────────
    PROPONENT_MAX_TOKENS: int  = get_int("PROPONENT_MAX_TOKENS", 1024)
    DECOMPOSITION_MAX_TOKENS: int = get_int("DECOMPOSITION_MAX_TOKENS", 2048)
    PROPONENT_TEMPERATURE: float  = get_float("PROPONENT_TEMPERATURE", 0.3)
    DECOMPOSER_TEMPERATURE: float = get_float("DECOMPOSER_TEMPERATURE", 0.1)

    # ── Sprint 2 ─────────────────────────────────────────────
    SKEPTIC_MAX_TOKENS: int    = get_int("SKEPTIC_MAX_TOKENS", 1024)
    SKEPTIC_TEMPERATURE: float = get_float("SKEPTIC_TEMPERATURE", 0.2)
    DEDUP_THRESHOLD: float     = get_float("DEDUP_THRESHOLD", 0.92)
    MAX_DEBATE_ROUNDS: int     = get_int("MAX_DEBATE_ROUNDS", 3)
    CONVERGENCE_THRESHOLD: float = get_float("CONVERGENCE_THRESHOLD", 0.85)
    STAGNATION_DELTA: float    = get_float("STAGNATION_DELTA", 0.05)

    # ── Sprint 3 ─────────────────────────────────────────────
    MODERATOR_MAX_TOKENS: int   = get_int("MODERATOR_MAX_TOKENS", 2048)
    MODERATOR_TEMPERATURE: float = get_float("MODERATOR_TEMPERATURE", 0.1)
    RETRIEVAL_MAX_RESULTS: int  = get_int("RETRIEVAL_MAX_RESULTS", 5)
    CLASSIFY_RELATIONS: bool    = get_bool("CLASSIFY_RELATIONS", True)

    # ── Sprint 4 ─────────────────────────────────────────────
    SYNTHESIS_MAX_TOKENS: int   = get_int("SYNTHESIS_MAX_TOKENS", 3000)
    SYNTHESIS_TEMPERATURE: float = get_float("SYNTHESIS_TEMPERATURE", 0.2)

    # ── Output ──────────────────────────────────────────────
    OUTPUT_DIR: Path           = Path(os.getenv("OUTPUT_DIR", "./outputs"))
    LOG_LEVEL: str             = os.getenv("LOG_LEVEL", "INFO")

    # ── LangSmith tracing ───────────────────────────────────
    LANGCHAIN_API_KEY: str     = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_TRACING_V2: bool = get_bool("LANGCHAIN_TRACING_V2", False)
    LANGCHAIN_PROJECT: str     = os.getenv("LANGCHAIN_PROJECT", "hybrid-debate-system")

    def validate(self) -> list[str]:
        errors: list[str] = []
        provider = self.PRIMARY_LLM_PROVIDER

        if provider == "openai" and not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is not set")
        if provider == "anthropic" and not self.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not set")
        if provider == "groq" and not self.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is not set")

        return errors


settings = Settings()