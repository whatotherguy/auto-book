"""Calibration management API endpoints."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import CalibrationProfile
from ..services.scoring.calibration.labels import load_labeled_dataset, save_labeled_dataset
from ..services.scoring.calibration.simulation import run_calibration_sweep

router = APIRouter(tags=["calibration"])
logger = logging.getLogger(__name__)

CALIBRATION_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "calibration"


class RunSweepRequest(BaseModel):
    dataset_name: str
    iterations: int = 1000
    jitter: float = 0.3


class CreateProfileRequest(BaseModel):
    name: str
    weights_json: str = ""
    thresholds_json: str = ""
    is_default: bool = False


@router.get("/calibration/profiles")
def list_profiles(session: Session = Depends(get_session)):
    profiles = session.exec(select(CalibrationProfile)).all()
    return [p.model_dump() for p in profiles]


@router.get("/calibration/profiles/{profile_id}")
def get_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.get(CalibrationProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile.model_dump()


@router.post("/calibration/profiles")
def create_profile(payload: CreateProfileRequest, session: Session = Depends(get_session)):
    if payload.is_default:
        _clear_default(session)
    profile = CalibrationProfile(
        name=payload.name,
        weights_json=payload.weights_json,
        thresholds_json=payload.thresholds_json,
        is_default=payload.is_default,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile.model_dump()


@router.patch("/calibration/profiles/{profile_id}/set-default")
def set_default_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.get(CalibrationProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    _clear_default(session)
    profile.is_default = True
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile.model_dump()


@router.delete("/calibration/profiles/{profile_id}")
def delete_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.get(CalibrationProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    session.delete(profile)
    session.commit()
    return {"ok": True, "deleted_id": profile_id}


@router.get("/calibration/datasets")
def list_datasets():
    CALIBRATION_DATA_DIR.mkdir(parents=True, exist_ok=True)
    datasets = []
    for path in CALIBRATION_DATA_DIR.iterdir():
        if path.is_dir() and (path / "labels.json").exists():
            labels = load_labeled_dataset(path)
            datasets.append({
                "name": path.name,
                "segment_count": len(labels),
            })
    return datasets


@router.get("/calibration/datasets/{dataset_name}")
def get_dataset(dataset_name: str):
    dataset_path = CALIBRATION_DATA_DIR / dataset_name
    if not (dataset_path / "labels.json").exists():
        raise HTTPException(status_code=404, detail="Dataset not found")
    labels = load_labeled_dataset(dataset_path)
    return {"name": dataset_name, "segments": labels}


@router.post("/calibration/sweep")
def run_sweep(payload: RunSweepRequest, session: Session = Depends(get_session)):
    dataset_path = CALIBRATION_DATA_DIR / payload.dataset_name
    if not (dataset_path / "labels.json").exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{payload.dataset_name}' not found")

    labeled = load_labeled_dataset(dataset_path)
    if not labeled:
        raise HTTPException(status_code=400, detail="Dataset is empty")

    result = run_calibration_sweep(
        labeled_segments=labeled,
        iterations=payload.iterations,
        jitter=payload.jitter,
    )

    # Auto-save best config as a CalibrationProfile
    if result.get("best_config"):
        _clear_default(session)
        profile = CalibrationProfile(
            name=f"sweep_{payload.dataset_name}_{payload.iterations}",
            weights_json=json.dumps(result["best_config"]),
            thresholds_json="{}",
            metrics_json=json.dumps(result.get("best_metrics", {})),
            is_default=True,
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        result["profile_id"] = profile.id

    return result


def _clear_default(session: Session) -> None:
    existing = session.exec(
        select(CalibrationProfile).where(CalibrationProfile.is_default == True)
    ).all()
    for p in existing:
        p.is_default = False
        session.add(p)
    session.flush()
