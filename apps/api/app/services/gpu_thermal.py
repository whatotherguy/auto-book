"""GPU thermal monitoring and protection for Windows (NVIDIA GPUs).

Polls nvidia-smi to read GPU temperature and provides throttling helpers
to prevent overheating during long transcription runs.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

# Defaults — overridable via env / settings
DEFAULT_TEMP_WARNING_C = 78
DEFAULT_TEMP_CRITICAL_C = 85
DEFAULT_COOLDOWN_PAUSE_SECONDS = 30
DEFAULT_POLL_INTERVAL_SECONDS = 10


def read_gpu_temperature() -> int | None:
    """Read current GPU temperature in Celsius via nvidia-smi.

    Returns None if nvidia-smi is unavailable or the query fails.
    Works on Windows (nvidia-smi.exe is on PATH for NVIDIA driver installs).
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().splitlines()[0])
    except FileNotFoundError:
        logger.debug("nvidia-smi not found — GPU thermal monitoring unavailable")
    except Exception as exc:
        logger.debug("GPU temperature read failed: %s", exc)
    return None


def read_gpu_power_draw() -> float | None:
    """Read current GPU power draw in watts via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip().splitlines()[0])
    except (FileNotFoundError, ValueError, Exception):
        pass
    return None


def read_gpu_utilization() -> int | None:
    """Read current GPU utilization percentage."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().splitlines()[0])
    except (FileNotFoundError, ValueError, Exception):
        pass
    return None


def get_gpu_thermal_status() -> dict[str, Any]:
    """Return a snapshot of GPU thermal state."""
    temp = read_gpu_temperature()
    power = read_gpu_power_draw()
    util = read_gpu_utilization()

    return {
        "temperature_c": temp,
        "power_draw_w": power,
        "utilization_pct": util,
        "monitoring_available": temp is not None,
    }


class ThermalGuard:
    """Monitors GPU temperature during long-running operations.

    Usage::

        guard = ThermalGuard(warning_temp=78, critical_temp=85)
        # Inside a processing loop:
        guard.check_and_throttle()  # blocks if GPU is too hot
    """

    def __init__(
        self,
        warning_temp: int = DEFAULT_TEMP_WARNING_C,
        critical_temp: int = DEFAULT_TEMP_CRITICAL_C,
        cooldown_seconds: int = DEFAULT_COOLDOWN_PAUSE_SECONDS,
        poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
        enabled: bool = True,
        progress_callback=None,
    ):
        self.warning_temp = warning_temp
        self.critical_temp = critical_temp
        self.cooldown_seconds = cooldown_seconds
        self.poll_interval = poll_interval
        self.enabled = enabled
        self.progress_callback = progress_callback
        self._last_check = 0.0
        self._total_cooldown_seconds = 0.0
        self.peak_temp: int | None = None

    def check_and_throttle(self, cancel_check=None) -> dict[str, Any]:
        """Check GPU temperature and pause if it exceeds thresholds.

        Returns a dict with the check result. Blocks (sleeps) if cooling
        is needed. Respects cancel_check to allow job cancellation during
        cooldown.
        """
        if not self.enabled:
            return {"action": "skip", "reason": "thermal_guard_disabled"}

        now = time.monotonic()
        if now - self._last_check < self.poll_interval:
            return {"action": "ok", "reason": "poll_interval_not_reached"}

        self._last_check = now
        temp = read_gpu_temperature()

        if temp is None:
            return {"action": "ok", "reason": "temperature_unavailable"}

        if self.peak_temp is None or temp > self.peak_temp:
            self.peak_temp = temp

        if temp >= self.critical_temp:
            logger.warning(
                "GPU temperature CRITICAL: %d°C (limit %d°C). Pausing for %ds cooldown.",
                temp, self.critical_temp, self.cooldown_seconds,
            )
            if self.progress_callback:
                self.progress_callback(
                    "thermal_cooldown", -1,
                    f"GPU too hot ({temp}°C). Cooling down for {self.cooldown_seconds}s..."
                )
            self._wait_for_cooldown(cancel_check)
            return {"action": "cooled", "temp_before": temp, "waited": self.cooldown_seconds}

        if temp >= self.warning_temp:
            logger.info("GPU temperature warning: %d°C (warning at %d°C)", temp, self.warning_temp)
            # Short pause to let the GPU breathe
            short_pause = min(5, self.cooldown_seconds // 3)
            if short_pause > 0:
                if self.progress_callback:
                    self.progress_callback(
                        "thermal_throttle", -1,
                        f"GPU warm ({temp}°C). Brief {short_pause}s pause."
                    )
                time.sleep(short_pause)
                self._total_cooldown_seconds += short_pause
            return {"action": "throttled", "temp": temp, "paused_seconds": short_pause}

        return {"action": "ok", "temp": temp}

    def _wait_for_cooldown(self, cancel_check=None) -> None:
        """Sleep in small increments, checking for cancellation and temp drop."""
        waited = 0
        while waited < self.cooldown_seconds:
            if cancel_check and cancel_check():
                return
            time.sleep(5)
            waited += 5
            self._total_cooldown_seconds += 5

            temp = read_gpu_temperature()
            if temp is not None and temp < self.warning_temp:
                logger.info("GPU cooled to %d°C after %ds — resuming.", temp, waited)
                return

        # Check temp after full cooldown
        temp = read_gpu_temperature()
        if temp is not None and temp >= self.critical_temp:
            logger.warning(
                "GPU still at %d°C after %ds cooldown. Continuing cautiously.",
                temp, self.cooldown_seconds,
            )

    @property
    def total_cooldown_seconds(self) -> float:
        return self._total_cooldown_seconds


def set_gpu_power_limit(watts: int | None) -> bool:
    """Attempt to set GPU power limit via nvidia-smi.

    Requires admin/elevated privileges on Windows. Returns True on success.
    Pass None to reset to default.
    """
    try:
        if watts is None:
            cmd = ["nvidia-smi", "-pl", "default"]
        else:
            cmd = ["nvidia-smi", "-pl", str(watts)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("GPU power limit set to %s", watts or "default")
            return True
        else:
            logger.warning("Failed to set GPU power limit: %s", result.stderr.strip())
            return False
    except (FileNotFoundError, Exception) as exc:
        logger.warning("Cannot set GPU power limit: %s", exc)
        return False
