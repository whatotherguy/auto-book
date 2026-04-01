import os
from pathlib import Path

from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parent
API_DIR = APP_DIR.parent
REPO_ROOT = API_DIR.parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "data" / "projects"
DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "audiobook_editor.db"
ENV_CANDIDATES = (API_DIR / ".env", REPO_ROOT / ".env")


def load_env_file() -> None:
    for env_path in ENV_CANDIDATES:
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]

            os.environ[key] = value


load_env_file()


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Audiobook Editor API")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}")
    data_root: Path = Path(os.getenv("DATA_ROOT", str(DEFAULT_DATA_ROOT)))
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "")  # "openai", "anthropic", or "" for disabled
    transcription_backend: str = os.getenv("TRANSCRIPTION_BACKEND", "local")  # "local" or "whisper_api"
    # GPU thermal protection
    gpu_thermal_protection: bool = os.getenv("GPU_THERMAL_PROTECTION", "true").strip().lower() in ("true", "1", "yes")
    gpu_temp_warning: int = int(os.getenv("GPU_TEMP_WARNING", "78"))
    gpu_temp_critical: int = int(os.getenv("GPU_TEMP_CRITICAL", "85"))
    gpu_cooldown_seconds: int = int(os.getenv("GPU_COOLDOWN_SECONDS", "30"))


settings = Settings()
settings.data_root.mkdir(parents=True, exist_ok=True)
DEFAULT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
