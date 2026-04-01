# Learn Book: Multi-Layer Audio Signal Scoring Engine

**Generated**: 2026-03-31
**Project**: auto-book (Audiobook Editor)
**Summary**: Built a 4-layer signal extraction, fusion, detection, and scoring pipeline that analyzes raw audiobook audio against manuscript text, detects 11 issue types using 15 heuristic detectors, computes 5 composite scores, generates editorial recommendations, clusters alternate takes, and provides an offline calibration harness — all integrated into an existing FastAPI/React full-stack application.

---

## What We Built

We extended an existing audiobook review tool with a comprehensive signal processing and heuristic scoring system. The system extracts audio features (RMS, spectral centroid, zero-crossing rate, pitch), runs voice activity detection, computes per-token prosody, then fuses these signals into enriched issue records. A 15-detector scoring engine produces 5 composite scores per issue, ranks alternate takes, and generates editorial recommendations. An offline Monte Carlo calibration system tunes detector weights against labeled datasets. The entire pipeline is exposed through new API endpoints and rendered in the React frontend with priority sorting, signal overlays, scoring breakdowns, and an alt-take selector panel.

---

## Architecture & Design Patterns

### Pipeline Pattern (Sequential Processing Pipeline)
- **What it is**: A design where data flows through a series of processing stages in order, each stage transforming or enriching the data before passing it to the next. Also called "Pipes and Filters."
- **How we used it**: `analyze_chapter.py` orchestrates 12 sequential stages from audio preparation through transcription, alignment, signal extraction (Layer 0), issue detection, signal fusion (Layer 1), alt-take clustering (Layer 2), scoring (Layer 3), triage, and persistence. Each stage has a progress percentage, cancellation check, and writes JSON artifacts.
- **Why it matters**: Pipelines make complex data transformations maintainable by isolating each concern into a stage. Stages can be tested independently, reordered, or replaced. Progress tracking becomes natural.
- **Interview context**: "Describe a data processing pipeline you've built." — Walk through how each stage has a single responsibility, how we used progress callbacks for observability, and how JSON artifact caching lets us skip expensive stages (like transcription) on re-analysis.

### Strategy Pattern (Detector Registry)
- **What it is**: A behavioral pattern where a family of algorithms is defined, encapsulated in classes/functions, and made interchangeable. The client code selects which algorithms to run at runtime.
- **How we used it**: `detector_registry.py` defines `ALL_DETECTORS` as a list of 15 `(name, function)` tuples. `run_all_detectors()` iterates through all registered detectors, passing the same feature/derived-feature dicts, and collects each `DetectorOutput`. Detectors can be individually enabled/disabled via config.
- **Why it matters**: Adding a new detector requires only writing the function and adding one line to the registry — no changes to the scoring pipeline. This is the Open/Closed Principle in action.
- **Interview context**: "How would you design a system that needs to support many pluggable algorithms?" — The detector registry is a textbook answer. Each detector has the same signature `(features, derived, config) -> DetectorOutput`, making them fully interchangeable.

### Composite Pattern (Weighted Score Aggregation)
- **What it is**: A pattern where individual components are composed into tree structures or weighted combinations to produce aggregate results. In scoring systems, this means combining multiple signals into composite metrics.
- **How we used it**: `composite.py` computes 5 composite scores by taking weighted sums of detector outputs. `_weighted_sum()` handles both positive weights (higher detector score = higher composite) and negative weights (higher detector score = lower composite, for quality/continuity inversions). Each composite includes score, confidence, component breakdown, and ambiguity flags.
- **Why it matters**: Composite scoring separates signal detection from decision-making. Detectors focus on "is this signal present?" while composites answer "what does the combination of signals mean?"
- **Interview context**: "How do you combine multiple scoring signals?" — Explain weighted aggregation with normalization, the handling of inverted weights for quality metrics, and how ambiguity flags surface conflicting signals.

### Adapter Pattern (Signal Fusion)
- **What it is**: A structural pattern that converts the interface of one system into an interface that another system expects. It bridges incompatible data formats.
- **How we used it**: `signal_fusion.py` adapts raw audio signals (point-in-time events), VAD segments (time ranges), and prosody features (per-token dicts) into a uniform set of JSON fields on each issue record (`audio_features_json`, `audio_signals_json`, `prosody_features_json`). Each builder function (`_build_audio_features`, `_build_audio_signals_flags`, `_build_prosody_features`) converts heterogeneous signal data into a consistent structure.
- **Why it matters**: Downstream consumers (detectors, UI) work with a single enriched issue record rather than querying three separate data sources with different time resolutions and formats.
- **Interview context**: "How did you handle integrating data from multiple sources with different schemas?" — Signal fusion as a dedicated adapter layer that normalizes heterogeneous data before it reaches the scoring engine.

### Observer/Callback Pattern (Progress Tracking)
- **What it is**: A pattern where an object notifies dependents of state changes. In pipelines, this manifests as progress callbacks that report status to external systems.
- **How we used it**: `set_job_progress(session, job, progress, step)` updates the database with the current pipeline stage and percentage. The frontend polls `GET /jobs/{id}` every 1.5 seconds to display real-time progress. `check_cancelled()` implements cooperative cancellation.
- **Why it matters**: Long-running jobs (3-8 minutes for transcription) need progress reporting for UX. Cooperative cancellation avoids killing processes mid-write.
- **Interview context**: "How do you handle long-running backend tasks with user feedback?" — Job queue with progress tracking, database-backed state, frontend polling, and cooperative cancellation.

### Repository Pattern (Persistence Layer)
- **What it is**: An abstraction that mediates between the domain layer and data mapping, providing a collection-like interface for accessing domain objects.
- **How we used it**: `persist_issue_models()` in `detect.py` maps dict-based issue records to SQLModel `Issue` objects. `_persist_signal_data()` in `analyze_chapter.py` handles `AudioSignal`, `VadSegment`, `AltTakeCluster`, `AltTakeMember`, and `ScoringResult` persistence. The pipeline works entirely with dicts; DB models are only used at the persistence boundary.
- **Why it matters**: Keeping domain logic (scoring, detection) free of ORM concerns. The scoring engine never imports SQLModel — it works with plain dicts. Only the persistence layer knows about the database.
- **Interview context**: "How do you separate business logic from data access?" — The scoring pipeline operates on dicts; persistence is a final, separate step.

### Builder Pattern (Envelope Construction)
- **What it is**: A creational pattern that constructs complex objects step by step, separating construction from representation.
- **How we used it**: `build_envelope()` in `envelope.py` assembles a `SegmentScoringEnvelope` from detector outputs, composite scores, recommendations, derived features, and baseline metadata. Each component is computed independently, then the builder composes them into the final structure.
- **Why it matters**: The envelope is the single authoritative record of everything the scoring engine computed for an issue. Building it from components keeps each step testable.
- **Interview context**: "How did you structure the output of a complex computation?" — The envelope pattern wraps heterogeneous results into one serializable structure.

### Chain of Responsibility (Recommendation Engine)
- **What it is**: A behavioral pattern where a request passes through a chain of handlers, and the first handler that can process it does so.
- **How we used it**: `generate_recommendation()` in `recommendations.py` evaluates composite scores through a priority-ordered chain of rules: splice_readiness > alt_take_member_count > pickup_score > mistake_score > ambiguous_signals > performance_quality > default. The first matching rule determines the action and priority.
- **Why it matters**: Deterministic, auditable decision-making. No ML black box — every recommendation can be traced to a specific rule and its triggering scores.
- **Interview context**: "Why did you use rules instead of ML for classification?" — Explainability, auditability, and the ability for editors to understand and trust recommendations. ML can tune the weights (calibration), but the rules remain transparent.

---

## Software Engineering Principles

### Separation of Concerns
- **What it is**: Each module should address a single concern. Changes to one concern shouldn't require changes to unrelated modules.
- **Where we applied it**: Signal extraction (`audio_analysis.py`, `vad.py`, `prosody.py`) knows nothing about scoring. Detectors (`detectors/*.py`) know nothing about persistence. The UI (`AltTakesPanel.tsx`, `IssueDetail.tsx`) knows nothing about how scores are computed — it just renders the data.
- **Interview context**: "The pipeline has four distinct layers. Layer 0 extracts signals, Layer 1 fuses them, Layer 2 clusters takes, Layer 3 scores everything. Each layer can be tested, modified, or replaced independently."

### Open/Closed Principle (SOLID)
- **What it is**: Software entities should be open for extension but closed for modification. New behavior should be added without changing existing code.
- **Where we applied it**: The detector registry. Adding a 16th detector requires writing one function and adding one tuple to `ALL_DETECTORS`. No changes to `run_all_detectors()`, `compute_all_composites()`, or `run_scoring_pipeline()`.
- **Interview context**: "How would you add a new detector?" — "Write the function, add it to the registry, add its weight to the relevant composite. Zero changes to the pipeline."

### Single Responsibility Principle (SOLID)
- **What it is**: A class/module should have one, and only one, reason to change.
- **Where we applied it**: Each detector file has one category (text, timing, audio, prosody, context). Each detector function does exactly one thing. `baseline.py` only computes statistics. `derived_features.py` only computes z-scores. `recommendations.py` only maps scores to actions.
- **Interview context**: Any question about code organization — point to how detector files are split by category, not by pipeline stage.

### Dependency Inversion Principle (SOLID)
- **What it is**: High-level modules should not depend on low-level modules. Both should depend on abstractions.
- **Where we applied it**: The scoring pipeline depends on the `DetectorOutput` dataclass interface, not on specific detector implementations. `run_all_detectors()` returns `dict[str, DetectorOutput]` — the composite scorer doesn't know which detectors produced which outputs. Calibration weights are loaded via an abstract profile lookup, not hardcoded.
- **Interview context**: "How does your scoring engine handle different detector configurations?" — Through CalibrationProfile injection. The pipeline loads weights at runtime from the database, falling back to config defaults.

### Don't Repeat Yourself (DRY)
- **What it is**: Every piece of knowledge should have a single, unambiguous representation in the system.
- **Where we applied it**: `_weighted_sum()` in `composite.py` is used by 4 of 5 composite score functions. `_find_signals_near()` in `signal_fusion.py` is the single proximity search used everywhere. Detection config constants in `detection_config.py` are the single source of truth for all thresholds.
- **Interview context**: "We have one weighted-sum function used by all composite scorers. Changing the aggregation logic requires one edit, not five."

### Fail Gracefully / Defensive Programming
- **What it is**: Software should handle unexpected inputs and failures without crashing, degrading functionality rather than failing completely.
- **Where we applied it**: `vad.py` returns empty segments if Silero VAD isn't installed. `prosody.py` skips tokens shorter than 50ms. `signal_fusion.py` handles missing JSON fields with defaults. The pipeline wraps everything in try/finally to mark failed jobs. Librosa functions have numpy fallbacks for when the library isn't installed.
- **Interview context**: "What happens if a dependency isn't available?" — "The system degrades gracefully. If VAD isn't installed, we get empty segments and skip VAD-dependent features. The pipeline still completes with reduced signal data."

---

## Technical Concepts & Terminology

### Feature Engineering
- **Definition**: The process of selecting, transforming, and creating input variables (features) from raw data to improve model/algorithm performance.
- **Our implementation**: `features.py` extracts a `RawFeatureCatalog` per issue from 5 dimensions (text, timing, audio, prosody, context). `derived_features.py` computes second-order features (z-scores, deltas, ratios) from raw features relative to a baseline.
- **Related terms**: Feature extraction, feature normalization, feature selection, domain features

### Z-Score Normalization
- **Definition**: Transforming a value to represent how many standard deviations it is from the mean: `z = (x - μ) / σ`. Makes features comparable across different scales.
- **Our implementation**: `_z_score()` in `derived_features.py` normalizes speech rate, F0, RMS, spectral centroid, and pause duration relative to chapter-level statistics from `baseline.py`. This makes a 200ms pause in a fast-paced chapter mean something different than in a slow chapter.
- **Related terms**: Standardization, statistical normalization, min-max scaling, feature scaling

### Adaptive Baseline
- **Definition**: A statistical baseline that adjusts to the characteristics of the current data rather than using fixed thresholds.
- **Our implementation**: `build_chapter_baseline()` computes per-chapter mean/std for speech rate, pitch, energy, and pauses. When a chapter has fewer than 30 segments, the baseline is flagged as unstable with a 50% blend ratio, allowing narrator-level statistics to compensate. This means the system adapts to different narrators' voices without manual tuning.
- **Related terms**: Adaptive thresholding, dynamic baseline, population statistics, narrator normalization

### Heuristic Scoring
- **Definition**: Using experience-based rules and weighted formulas rather than trained ML models to make decisions. Heuristics are interpretable, tunable, and don't require training data.
- **Our implementation**: All 15 detectors use hand-crafted rules (e.g., "if crest factor > 12dB and ZCR > 0.3 and centroid > 2kHz, it's a click"). Composite scores use configurable weighted sums. Recommendations use a deterministic priority chain.
- **Related terms**: Rule-based system, expert system, deterministic classification, interpretable AI

### Monte Carlo Simulation
- **Definition**: A computational technique that uses random sampling to obtain numerical results, typically used to optimize parameters or estimate probabilities.
- **Our implementation**: `run_calibration_sweep()` in `simulation.py` runs 1000 iterations where each iteration: samples random weights around defaults (±30% jitter), normalizes them, re-scores all labeled segments, evaluates against ground truth, and tracks the best configuration. This optimizes the 50+ weight parameters without gradient computation.
- **Related terms**: Random search, hyperparameter optimization, grid search, Bayesian optimization, stochastic optimization

### Composite Scoring / Multi-Criteria Decision Analysis
- **Definition**: Combining multiple individual scores or criteria into aggregate metrics for decision-making, often using weighted sums.
- **Our implementation**: 5 composite scores combine 15 detector outputs using domain-specific weight vectors. Negative weights invert the relationship (higher detector score = lower composite score), used for quality and continuity metrics. Each composite tracks its component breakdown for explainability.
- **Related terms**: Weighted scoring model, multi-attribute utility theory, decision matrix, scoring rubric

### Signal Processing / Digital Signal Processing (DSP)
- **Definition**: The mathematical manipulation of signals (audio, in our case) to extract information, detect patterns, or transform the data.
- **Our implementation**: `audio_analysis.py` computes: RMS energy (frame-level power), zero-crossing rate (noise vs tonal content), spectral centroid (brightness), onset strength (transient detection), crest factor (peak-to-RMS ratio for click detection). All implemented with windowed frame analysis using numpy FFT.
- **Related terms**: FFT, spectral analysis, frame analysis, windowing, hop length, sample rate

### Voice Activity Detection (VAD)
- **Definition**: The task of determining which segments of audio contain human speech versus silence/noise. Used to segment audio and find speech boundaries.
- **Our implementation**: `vad.py` loads the Silero VAD model via `torch.hub`, processes audio at 16kHz, and returns speech segments with start/end timestamps and speech probability. Used downstream to find silences between takes and detect non-speech markers.
- **Related terms**: Speech detection, speech segmentation, silence detection, endpoint detection

### Prosody Analysis
- **Definition**: The study of speech rhythm, stress, and intonation — specifically pitch (F0), speech rate, energy contour, and pausing patterns.
- **Our implementation**: `prosody.py` extracts per-token F0 using librosa's pyin algorithm, computes speech rate (words per second), energy contour (RMS per frame), and inter-token pause durations. Contours are capped at 50 frames for storage efficiency.
- **Related terms**: F0 extraction, pitch tracking, pyin, speech rate, energy envelope, intonation

### Clustering Algorithm
- **Definition**: Grouping data points that share similar characteristics. In our case, grouping audio segments that cover the same manuscript text.
- **Our implementation**: `detect_alt_takes()` uses a greedy clustering approach: sort by manuscript position, then for each issue check if it overlaps an existing cluster (manuscript range overlap + time proximity ≤ 15s + word overlap ≥ 60%). This is a custom domain-specific clustering, not k-means or DBSCAN, because the similarity metric combines spatial (manuscript position), temporal (audio time), and textual dimensions.
- **Related terms**: Greedy clustering, spatial clustering, multi-dimensional similarity, agglomerative clustering

### JSON Blob Storage (Semi-Structured Data)
- **Definition**: Storing complex, variable-structure data as serialized JSON strings within relational database columns, providing flexibility without schema changes.
- **Our implementation**: Issue records store `audio_features_json`, `audio_signals_json`, and `prosody_features_json` as JSON strings. `ScoringResult` stores `composite_scores_json`, `detector_outputs_json`, `recommendation_json`, and `derived_features_json`. This lets us evolve the scoring schema without database migrations.
- **Related terms**: Document storage, EAV pattern, schemaless storage, JSONB, semi-structured data

### Envelope Pattern
- **Definition**: Wrapping all metadata and computed results about an entity into a single self-contained document/structure, so consumers get everything they need in one object.
- **Our implementation**: `SegmentScoringEnvelope` (built in `envelope.py`) contains: issue reference, all 15 detector outputs, all 5 composite scores, the editorial recommendation, derived features, baseline reference, and denormalized scalar scores. The frontend receives one envelope per issue and can render the full scoring breakdown.
- **Related terms**: Data transfer object (DTO), aggregate, message envelope, fat model

---

## API & Protocol Concepts

### RESTful Resource Design
- **Standard**: REST (Representational State Transfer) — resources identified by URLs, manipulated via HTTP verbs.
- **Our implementation**: New endpoints follow REST conventions: `GET /chapters/{id}/audio-signals` (collection resource), `GET /chapters/{id}/alt-take-clusters` (nested collection), `PATCH /alt-take-clusters/{id}/preferred` (partial update on a resource). The `PATCH` for preferred take selection updates only the `preferred_issue_id` field and cascades status changes to member issues.

### Idempotency
- **Standard**: An operation that produces the same result regardless of how many times it's called.
- **Our implementation**: `PATCH /alt-take-clusters/{id}/preferred` is idempotent — calling it twice with the same `preferred_issue_id` produces the same cluster state. The calibration sweep `POST /calibration/sweep` is not idempotent (random sampling), but it's explicitly a "run this process" action, not a resource mutation.

### Query Parameter vs Body Design
- **Our implementation**: The `auto_approve_threshold` parameter on `POST /chapters/{id}/exports/edited-wav` is a query parameter (optional modifier on the action) rather than a body field, following the convention that query params modify behavior while body contains the primary payload.

---

## Data & Database Concepts

### Database Migration (Schema Evolution)
- **Definition**: The process of evolving a database schema over time using versioned, reversible scripts.
- **Our implementation**: `a1b2c3d4e5f6_add_signal_scoring_tables.py` is an Alembic migration that creates 6 new tables (`audiosignal`, `vadsegment`, `alttakecluster`, `alttakemember`, `scoringresult`, `calibrationprofile`) and adds 4 columns to the existing `issue` table. Both `upgrade()` and `downgrade()` are defined, making the migration fully reversible.

### Foreign Key Relationships & Referential Integrity
- **Our implementation**: `AltTakeMember` has foreign keys to both `AltTakeCluster` and `Issue`, creating a many-to-many relationship through a join table. `AltTakeCluster.preferred_issue_id` is a nullable FK to `Issue`, representing an optional "has-a" relationship. All FKs are indexed for query performance.

### Denormalization for Performance
- **Definition**: Intentionally duplicating data to avoid expensive joins at query time.
- **Our implementation**: `ScoringResult` stores denormalized `mistake_score`, `pickup_score`, `performance_score`, and `splice_score` as top-level float columns even though the same data exists in `composite_scores_json`. This allows `ORDER BY mistake_score DESC` without JSON parsing. The `priority` field is similarly denormalized from the recommendation JSON.

### ORM (Object-Relational Mapping)
- **Definition**: A technique that maps database tables to programming language objects, abstracting SQL behind object-oriented interfaces.
- **Our implementation**: SQLModel (built on SQLAlchemy + Pydantic) maps all 10 tables to Python classes with type hints. `session.add()`, `session.flush()`, `session.commit()` handle persistence. `.model_dump()` serializes to dicts for API responses. The `flush()` call in `_persist_signal_data()` is important — it generates the auto-incremented `id` before we reference it in child records.

---

## Testing Concepts

### Unit Testing with Boundary Isolation
- **Definition**: Testing individual units of code in isolation, with clear boundaries between what's tested and what's mocked.
- **Our implementation**: Detector tests (`test_scoring_detectors.py`) test each of the 15 detectors independently by passing feature/derived dicts directly — no database, no file I/O, no pipeline setup. This makes tests fast and deterministic.

### Property-Based Test Design
- **Definition**: Testing that outputs satisfy expected properties rather than matching exact values.
- **Our implementation**: Tests verify properties like "score is between 0 and 1", "triggered is True when score exceeds threshold", "15 detectors returned", "weights sum to 1.0". This is more robust than asserting exact float values that might change with tuning.

### Test Fixture Minimalism
- **Definition**: Using the smallest possible test data that exercises the behavior under test.
- **Our implementation**: `test_audio_analysis.py` creates a 1-second WAV file with a sine wave to test the full `analyze_audio_signals()` function. `test_alt_takes.py` uses 2-token manuscripts and 2-issue lists — the minimum to form a cluster.

### Integration vs Unit Test Boundary
- **Our implementation**: `test_audio_analysis.py::test_analyze_audio_signals_returns_list` is an integration test (creates a real WAV file, runs the full analysis pipeline). `test_scoring_detectors.py` tests are pure unit tests (no I/O, no dependencies). This separation lets us run unit tests in milliseconds and integration tests only when needed.

---

## Performance & Optimization

### Lazy Loading / Deferred Initialization
- **Definition**: Delaying the creation of an object or computation until it's first needed.
- **Our implementation**: The Silero VAD model in `vad.py` uses module-level `_vad_model = None` with a `_load_vad_model()` function that caches the model on first call. The scoring pipeline lazy-imports `run_scoring_pipeline` inside the pipeline function to avoid circular imports and defer the import cost.

### Caching Artifacts
- **Definition**: Saving expensive computation results to disk so they can be reused without recomputation.
- **Our implementation**: Every pipeline stage writes JSON artifacts to the chapter's `analysis/` directory (`audio_signals.json`, `vad_segments.json`, `prosody_features.json`, `scoring_result.json`). On re-analysis, these could be checked for freshness and skipped.

### Graceful Degradation
- **Definition**: A system that continues operating with reduced functionality when a component fails or is unavailable.
- **Our implementation**: `audio_analysis.py` falls back from `librosa.load()` to Python's `wave` module if librosa isn't installed. `vad.py` returns empty segments if torch isn't available. `prosody.py` returns null F0 values if pyin fails. The pipeline continues with whatever signals are available.

### Contour Length Capping
- **Our implementation**: `MAX_CONTOUR_LENGTH = 50` in `prosody.py` caps F0 and energy contours to 50 frames regardless of segment length. This prevents storage bloat from long segments while preserving enough shape information for quality assessment. A pragmatic space/information trade-off.

---

## Key Takeaways for Interviews

- "I designed a 4-layer signal processing pipeline that extracts audio features, fuses multi-modal signals, clusters alternate takes, and scores issues using 15 heuristic detectors — all with adaptive baselines and configurable weights."
- "I implemented a composable detector registry using the Strategy pattern — adding new detectors requires one function and one registry entry, with zero changes to the pipeline."
- "I built a Monte Carlo calibration system that optimizes 50+ weight parameters by random sampling against labeled datasets, achieving measurable F1 improvements."
- "I used z-score normalization with adaptive per-chapter baselines so the scoring system works across different narrators without manual threshold tuning."
- "I designed the system for explainability — every recommendation traces back to specific detector outputs, component scores, and triggering reasons, so editors can understand and trust the system's suggestions."
- "I implemented graceful degradation throughout — if GPU libraries aren't installed, the system falls back to CPU alternatives and still produces useful results."
- "I built a full-stack feature across FastAPI (new models, services, API endpoints), React (new components, state management, data fetching), and SQLite (Alembic migration with 6 new tables), coordinating the data contract between backend and frontend."
- "I created a comprehensive test suite of 100+ tests covering all 15 detectors individually, composite scoring, recommendation rules, calibration metrics, signal fusion, and audio analysis — all with minimal fixtures and property-based assertions."

---

## Concepts to Explore Further

- **Bayesian Optimization**: A more sample-efficient alternative to Monte Carlo for calibration weight tuning. Would converge faster than random sampling on the 50+ parameter space.
- **Speaker Diarization**: Extending VAD to identify different speakers. Would improve alt-take detection when narrators do character voices.
- **Mel-Frequency Cepstral Coefficients (MFCCs)**: Standard audio features used in speech recognition. Could improve room tone shift and continuity detection.
- **Online Learning / Incremental Calibration**: Updating calibration weights as editors approve/reject issues, rather than batch offline sweeps.
- **A/B Testing Framework**: Comparing different CalibrationProfiles by routing chapters to different weight configurations and measuring editor agreement rates.
- **WebSocket Progress Streaming**: Replacing the 1.5-second polling interval with server-push progress updates for the analysis pipeline.
- **Feature Importance / SHAP Values**: Analyzing which detectors contribute most to correct recommendations, guiding weight tuning and detector development.
- **Time-Series Anomaly Detection**: Treating the audio feature stream as a time series and applying anomaly detection algorithms (Isolation Forest, autoencoders) instead of hand-crafted thresholds.
