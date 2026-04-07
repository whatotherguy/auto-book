FALSE_START_MIN_SPAN = 2
FALSE_START_MAX_SPAN = 6

FALSE_START_CONFIDENCE_BY_SPAN = {
    2: 0.96,
    3: 0.93,
    4: 0.9,
    5: 0.86,
    6: 0.82,
}

REPETITION_MIN_SPAN = 2
REPETITION_MAX_SPAN = 12

REPETITION_CONFIDENCE_BY_SPAN = {
    2: 0.94,
    3: 0.92,
    4: 0.9,
    5: 0.88,
    6: 0.86,
    7: 0.84,
    8: 0.82,
    9: 0.8,
    10: 0.78,
    11: 0.76,
    12: 0.74,
}

LONG_PAUSE_THRESHOLD_MS = 1200  # Can be overridden per-project via project settings
LONG_PAUSE_MID_SENTENCE_CONFIDENCE = 0.85
LONG_PAUSE_SENTENCE_BOUNDARY_CONFIDENCE = 0.60
LONG_PAUSE_CONFIDENCE = LONG_PAUSE_MID_SENTENCE_CONFIDENCE
MISSING_TEXT_CONFIDENCE = 0.72
UNCERTAIN_ALIGNMENT_CONFIDENCE = 0.58
PICKUP_RESTART_CONFIDENCE = 0.72

ISSUE_STATUS_APPROVED_CONFIDENCE_THRESHOLD = 0.85
ISSUE_STATUS_PENDING_CONFIDENCE_THRESHOLD = 0.70

# === Signal Extraction Thresholds ===
CLICK_MIN_DURATION_MS = 5
CLICK_MAX_DURATION_MS = 80
CLICK_CREST_FACTOR_THRESHOLD = 12.0
CLICK_SPECTRAL_CENTROID_MIN_HZ = 2000
CLICK_ZCR_THRESHOLD = 0.3
CLICK_ONSET_STRENGTH_THRESHOLD = 3.0
ABRUPT_CUTOFF_RMS_DROP_FACTOR = 6.0

# === Signal Fusion Thresholds ===
PICKUP_SILENCE_BEFORE_MS = 300
PICKUP_CLICK_PROXIMITY_MS = 2000
NON_SPEECH_MARKER_CONFIDENCE = 0.90
PICKUP_CANDIDATE_BASE_CONFIDENCE = 0.40

# === Corroboration-First Thresholds ===
# Pickup candidates require stronger evidence to become primary issues.
# Tightened thresholds reduce false positives from pure audio signals.
PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY = 0.75  # Raised from effective ~0.65
PICKUP_CANDIDATE_REQUIRE_DUAL_SIGNAL = True  # Require click+cutoff or multiple signals
PICKUP_CANDIDATE_SILENCE_BOOST_MS = 800  # Silence must be longer for confidence boost
NON_SPEECH_MARKER_IS_SECONDARY = True  # Non-speech markers are secondary by default

# === Alt-Take Clustering ===
ALT_TAKE_MAX_GAP_MS = 15000
ALT_TAKE_MIN_TEXT_OVERLAP = 0.6
ALT_TAKE_MIN_CLUSTER_SIZE = 2

# === Performance Variant Detection ===
PERFORMANCE_VARIANT_RATE_DIFF = 0.3
PERFORMANCE_VARIANT_F0_DIFF_HZ = 20
PERFORMANCE_VARIANT_ENERGY_RATIO = 1.5

# === Composite Scoring Weights (defaults, overridden by CalibrationProfile) ===
MISTAKE_WEIGHTS = {
    "text_mismatch": 0.35, "repeated_phrase": 0.20, "skipped_text": 0.20,
    "abnormal_pause": 0.10, "rushed_delivery": 0.05, "clipping": 0.05,
    "click_transient": 0.05,
}
PICKUP_WEIGHTS = {
    "pickup_pattern": 0.35, "restart_gap": 0.25, "click_transient": 0.15,
    "repeated_phrase": 0.10, "abnormal_pause": 0.10, "punch_in_boundary": 0.05,
}
PERFORMANCE_WEIGHTS = {
    "flat_delivery": -0.30, "weak_landing": -0.20, "cadence_drift": -0.15,
    "rushed_delivery": -0.15, "clipping": -0.10, "room_tone_shift": -0.10,
}
CONTINUITY_WEIGHTS = {
    "continuity_mismatch": -0.40, "room_tone_shift": -0.25,
    "punch_in_boundary": -0.20, "cadence_drift": -0.15,
}
TAKE_PREFERENCE_WEIGHTS = {
    "text_accuracy": 0.35, "performance_quality": 0.30,
    "continuity_fit": 0.25, "splice_readiness": 0.10,
}
