"""DetectorOutput and DetectorConfig dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DetectorConfig:
    """Configuration for a single detector."""
    name: str
    enabled: bool = True
    threshold: float = 0.3
    weight: float = 1.0


@dataclass
class DetectorOutput:
    """Output from a single detector."""
    detector_name: str
    score: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    features_used: dict = field(default_factory=dict)
    triggered: bool = False

    def to_dict(self) -> dict:
        return {
            "detector_name": self.detector_name,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
            "features_used": self.features_used,
            "triggered": self.triggered,
        }
