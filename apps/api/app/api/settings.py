"""Settings endpoint for reading and updating runtime configuration.

API keys are write-only — the GET endpoint returns whether they are set
but never returns the actual key values.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import persist_to_env_file, settings
from ..services.gpu_thermal import get_gpu_thermal_status
from ..services.transcribe import detect_gpu
from ..services.transcribe_api import is_whisper_api_available
from ..services.triage import is_triage_available

router = APIRouter(prefix="/settings", tags=["settings"])


class GpuThermalStatus(BaseModel):
    temperature_c: int | None = None
    power_draw_w: float | None = None
    utilization_pct: int | None = None
    monitoring_available: bool = False


class ThermalProtectionSettings(BaseModel):
    enabled: bool = True
    warning_temp_c: int = 78
    critical_temp_c: int = 85
    cooldown_seconds: int = 30


class SettingsResponse(BaseModel):
    transcription_backend: str
    llm_provider: str
    has_openai_key: bool
    has_anthropic_key: bool
    gpu_available: bool
    gpu_name: str | None
    gpu_vram_gb: float | None = None
    whisper_api_available: bool
    triage_available: bool
    gpu_thermal: GpuThermalStatus
    thermal_protection: ThermalProtectionSettings


class SettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: str | None = None
    transcription_backend: str | None = None
    gpu_thermal_protection: bool | None = None
    gpu_temp_warning: int | None = None
    gpu_temp_critical: int | None = None
    gpu_cooldown_seconds: int | None = None


@router.get("")
def get_settings() -> SettingsResponse:
    gpu = detect_gpu()
    thermal = get_gpu_thermal_status()
    return SettingsResponse(
        transcription_backend=settings.transcription_backend,
        llm_provider=settings.llm_provider,
        has_openai_key=bool(settings.openai_api_key),
        has_anthropic_key=bool(settings.anthropic_api_key),
        gpu_available=gpu["available"],
        gpu_name=gpu.get("name"),
        gpu_vram_gb=gpu.get("vram_gb"),
        whisper_api_available=is_whisper_api_available(),
        triage_available=is_triage_available(),
        gpu_thermal=GpuThermalStatus(**thermal),
        thermal_protection=ThermalProtectionSettings(
            enabled=settings.gpu_thermal_protection,
            warning_temp_c=settings.gpu_temp_warning,
            critical_temp_c=settings.gpu_temp_critical,
            cooldown_seconds=settings.gpu_cooldown_seconds,
        ),
    )


@router.patch("")
def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    import os

    def _apply(env_key: str, value: str) -> None:
        os.environ[env_key] = value
        persist_to_env_file(env_key, value)

    if payload.openai_api_key is not None:
        settings.openai_api_key = payload.openai_api_key
        _apply("OPENAI_API_KEY", payload.openai_api_key)
    if payload.anthropic_api_key is not None:
        settings.anthropic_api_key = payload.anthropic_api_key
        _apply("ANTHROPIC_API_KEY", payload.anthropic_api_key)
    if payload.llm_provider is not None:
        settings.llm_provider = payload.llm_provider
        _apply("LLM_PROVIDER", payload.llm_provider)
    if payload.transcription_backend is not None:
        settings.transcription_backend = payload.transcription_backend
        _apply("TRANSCRIPTION_BACKEND", payload.transcription_backend)
    if payload.gpu_thermal_protection is not None:
        settings.gpu_thermal_protection = payload.gpu_thermal_protection
        _apply("GPU_THERMAL_PROTECTION", "true" if payload.gpu_thermal_protection else "false")
    if payload.gpu_temp_warning is not None:
        settings.gpu_temp_warning = payload.gpu_temp_warning
        _apply("GPU_TEMP_WARNING", str(payload.gpu_temp_warning))
    if payload.gpu_temp_critical is not None:
        settings.gpu_temp_critical = payload.gpu_temp_critical
        _apply("GPU_TEMP_CRITICAL", str(payload.gpu_temp_critical))
    if payload.gpu_cooldown_seconds is not None:
        settings.gpu_cooldown_seconds = payload.gpu_cooldown_seconds
        _apply("GPU_COOLDOWN_SECONDS", str(payload.gpu_cooldown_seconds))

    return get_settings()


@router.get("/gpu-status")
def get_gpu_status():
    """Live GPU status for dashboard polling."""
    gpu = detect_gpu()
    thermal = get_gpu_thermal_status()
    return {
        **gpu,
        **thermal,
        "thermal_protection_enabled": settings.gpu_thermal_protection,
    }
