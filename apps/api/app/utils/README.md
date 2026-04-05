# utils

Small, dependency-free helpers shared across the backend.

## Files

| File | Description |
|------|-------------|
| `timecode.py` | `ms_to_timecode(ms: int) -> str` — convert a millisecond offset to `HH:MM:SS.mmm` format for display and export |
| `tokenization.py` | `tokenize(text)`, `build_text_token_records(text)` — whitespace-split tokenisation and `TokenRecord` TypedDict construction used by the alignment pipeline |

## Notes

- Neither module imports from the rest of the app, making them safe to use anywhere without circular-import concerns.
- `ms_to_timecode` raises `ValueError` for negative inputs — callers should clamp to 0 before converting offsets from imperfect alignment data.
