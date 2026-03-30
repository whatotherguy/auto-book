"""Settings endpoint for reading and updating runtime configuration.

API keys are write-only — the GET endpoint returns whether they are set
but never returns the actual key values.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..services.transcribe import detect_gpu
from ..services.transcribe_api import is_whisper_api_available
from ..services.triage import is_triage_available

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    transcription_backend: str
    llm_provider: str
    has_openai_key: bool
    has_anthropic_key: bool
    gpu_available: bool
    gpu_name: str | None
    whisper_api_available: bool
    triage_available: bool


class SettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: str | None = None
    transcription_backend: str | None = None


@router.get("")
def get_settings() -> SettingsResponse:
    gpu = detect_gpu()
    return SettingsResponse(
        transcription_backend=settings.transcription_backend,
        llm_provider=settings.llm_provider,
        has_openai_key=bool(settings.openai_api_key),
        has_anthropic_key=bool(settings.anthropic_api_key),
        gpu_available=gpu["available"],
        gpu_name=gpu.get("name"),
        whisper_api_available=is_whisper_api_available(),
        triage_available=is_triage_available(),
    )


@router.patch("")
def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    import os

    if payload.openai_api_key is not None:
        settings.openai_api_key = payload.openai_api_key
        os.environ["OPENAI_API_KEY"] = payload.openai_api_key
    if payload.anthropic_api_key is not None:
        settings.anthropic_api_key = payload.anthropic_api_key
        os.environ["ANTHROPIC_API_KEY"] = payload.anthropic_api_key
    if payload.llm_provider is not None:
        settings.llm_provider = payload.llm_provider
        os.environ["LLM_PROVIDER"] = payload.llm_provider
    if payload.transcription_backend is not None:
        settings.transcription_backend = payload.transcription_backend
        os.environ["TRANSCRIPTION_BACKEND"] = payload.transcription_backend

    return get_settings()
