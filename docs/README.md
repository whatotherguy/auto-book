# docs

Project-level documentation. These documents describe the overall design, API contract, heuristic rules, and test strategy for the Audiobook Editor.

## Contents

| File | Description |
|------|-------------|
| `ARCHITECTURE.md` | High-level system architecture: data flow, app boundaries, storage layout, and design principles |
| `API_CONTRACT.md` | REST API contract — all endpoints, request/response shapes, and status codes |
| `ISSUE_HEURISTICS.md` | Detailed specification of all 7 issue types (`false_start`, `repetition`, `pickup_restart`, `substitution`, `missing_text`, `long_pause`, `uncertain_alignment`), their detection heuristics, confidence rules, and expected output fields |
| `BUILD_PLAN.md` | Incremental build plan and feature roadmap |
| `TEST_PLAN.md` | Test strategy, coverage goals, and descriptions of key test scenarios |

## Related top-level documents

| File | Description |
|------|-------------|
| `../README.md` | Quick-start guide and stack overview |
| `../AGENTS.md` | AI-agent coding rules and project constraints |
| `../BLITZ_CALIBRATION_HARNESS.md` | Full specification for the offline calibration system |
| `../UNIFIED_BUILD_PACKET.md` | Consolidated build and deployment reference |
| `../signal_scoring_engine_learn_book.md` | In-depth explanation of the signal scoring engine design |
