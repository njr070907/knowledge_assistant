from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


SERVER_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SERVER_ROOT / ".env")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("ZHILIU_HOST", "127.0.0.1")
    port: int = int(os.getenv("ZHILIU_PORT", "8765"))
    model_name: str = os.getenv("ZHILIU_ASR_MODEL", "small")
    device: str = os.getenv("ZHILIU_ASR_DEVICE", "cpu")
    compute_type: str = os.getenv("ZHILIU_ASR_COMPUTE_TYPE", "int8")
    cpu_threads: int = int(os.getenv("ZHILIU_CPU_THREADS", "8"))
    chunk_seconds: float = float(os.getenv("ZHILIU_CHUNK_SECONDS", "4.0"))
    language: str = os.getenv("ZHILIU_LANGUAGE", "zh")
    topic_seconds: float = float(os.getenv("ZHILIU_TOPIC_SECONDS", "36"))
    data_dir: Path = Path(os.getenv("ZHILIU_DATA_DIR", SERVER_ROOT / "data"))
    llm_enabled: bool = env_flag("ZHILIU_LLM_ENABLED")
    llm_base_url: str = os.getenv("ZHILIU_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    llm_model: str = os.getenv("ZHILIU_LLM_MODEL", "local-model")
    llm_timeout_seconds: float = float(os.getenv("ZHILIU_LLM_TIMEOUT", "120"))
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_parent_page_id: str = os.getenv("NOTION_PARENT_PAGE_ID", "")
    notion_api_version: str = os.getenv("NOTION_API_VERSION", "2026-03-11")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "zhiliu.sqlite3"


settings = Settings()
