from __future__ import annotations

import json
from pathlib import Path

from .audio import copy_audio_to_working


def prepare_working_audio_copy(source_audio_path: str | None, working_dir: Path) -> Path | None:
    if not source_audio_path:
        return None

    source_path = Path(source_audio_path)
    if not source_path.exists():
        return None

    return copy_audio_to_working(source_path, working_dir / source_path.name)


def write_json_artifact(target_path: Path, payload: object) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
