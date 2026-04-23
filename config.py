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
    PROPONENT_MAX_TOKENS: int  = int(os.getenv("PROPONENT_MAX_TOKENS", "1024"))
    DECOMPOSITION_MAX_TOKENS: int = int(os.getenv("DECOMPOSITION_MAX_TOKENS", "2048"))
    PROPONENT_TEMPERATURE: float  = float(os.getenv("PROPONENT_TEMPERATURE", "0.3"))
    DECOMPOSER_TEMPERATURE: float = float(os.getenv("DECOMPOSER_TEMPERATURE", "0.1"))

    # ── Sprint 2 ─────────────────────────────────────────────
    SKEPTIC_MAX_TOKENS: int    = int(os.getenv("SKEPTIC_MAX_TOKENS", "1024"))
    SKEPTIC_TEMPERATURE: float = float(os.getenv("SKEPTIC_TEMPERATURE", "0.2"))
    DEDUP_THRESHOLD: float     = float(os.getenv("DEDUP_THRESHOLD", "0.92"))
    MAX_DEBATE_ROUNDS: int     = int(os.getenv("MAX_DEBATE_ROUNDS", "3"))
    CONVERGENCE_THRESHOLD: float = float(os.getenv("CONVERGENCE_THRESHOLD", "0.85"))
    STAGNATION_DELTA: float    = float(os.getenv("STAGNATION_DELTA", "0.05"))

    # ── Sprint 3 ─────────────────────────────────────────────
    MODERATOR_MAX_TOKENS: int   = int(os.getenv("MODERATOR_MAX_TOKENS", "2048"))
    MODERATOR_TEMPERATURE: float = float(os.getenv("MODERATOR_TEMPERATURE", "0.1"))
    RETRIEVAL_MAX_RESULTS: int  = int(os.getenv("RETRIEVAL_MAX_RESULTS", "5"))
    # Whether to call LLM to classify each snippet's relation (SUPPORTS/CONTRADICTS/UNRELATED)
    # Set to false to skip relation classification LLM calls (faster, less accurate)
    CLASSIFY_RELATIONS: bool    = os.getenv("CLASSIFY_RELATIONS", "true").lower() == "true"

    # ── Sprint 4 ─────────────────────────────────────────────
    SYNTHESIS_MAX_TOKENS: int   = int(os.getenv("SYNTHESIS_MAX_TOKENS", "3000"))
    SYNTHESIS_TEMPERATURE: float = float(os.getenv("SYNTHESIS_TEMPERATURE", "0.2"))

    # ── Output ──────────────────────────────────────────────
    OUTPUT_DIR: Path           = Path(os.getenv("OUTPUT_DIR", "./outputs"))
    LOG_LEVEL: str             = os.getenv("LOG_LEVEL", "INFO")

    # ── LangSmith tracing ───────────────────────────────────
    LANGCHAIN_API_KEY: str     = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_TRACING_V2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_PROJECT: str     = os.getenv("LANGCHAIN_PROJECT", "hybrid-debate-system")

    def validate(self) -> list[str]:
        """Return a list of missing critical keys."""
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
