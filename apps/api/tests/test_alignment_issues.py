from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Issue
from app.services.align import build_alignment, build_manuscript_tokens, build_spoken_tokens
from app.services.detect import build_issue_records, detect_alignment_issues, detect_pickup_restarts, persist_issue_models


def _timed_tokens(text: str) -> list[dict[str, int | str]]:
    tokens = []
    for index, word in enumerate(text.split()):
        tokens.append(
            {
                "text": word,
                "normalized": word,
                "start_ms": index * 1000,
                "end_ms": index * 1000 + 500,
            }
        )
    return tokens


def test_detect_missing_text_from_alignment_delete():
    manuscript_tokens = build_manuscript_tokens("the quick brown fox")
    spoken_tokens = build_manuscript_tokens("the fox")

    alignment = build_alignment(manuscript_tokens, spoken_tokens)
    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)

    assert any(issue["type"] == "missing_text" for issue in issues)


def test_detect_insert_as_uncertain_alignment():
    manuscript_tokens = build_manuscript_tokens("the quick fox")
    spoken_tokens = build_manuscript_tokens("the quick extra fox")

    alignment = build_alignment(manuscript_tokens, spoken_tokens)
    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)

    assert any(issue["type"] in {"uncertain_alignment", "pickup_restart"} for issue in issues)


def test_alignment_normalization_handles_honorifics():
    manuscript_tokens = build_manuscript_tokens("Dr. Smith")
    spoken_tokens = build_spoken_tokens(
        {
            "words": [
                {"word": "doctor", "start": 0.0, "end": 0.2},
                {"word": "smith", "start": 0.2, "end": 0.4},
            ]
        }
    )

    alignment = build_alignment(manuscript_tokens, spoken_tokens)

    assert alignment["match_ratio"] == 1.0
    assert any(match["op"] == "equal" for match in alignment["matches"])


def test_detect_pickup_restart_mid_chapter_anchor():
    manuscript_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta eta theta iota kappa")
    spoken_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta gamma delta eta theta gamma delta iota kappa")
    alignment = {
        "matches": [
            {
                "op": "insert",
                "manuscript_start": 2,
                "manuscript_end": 2,
                "spoken_start": 6,
                "spoken_end": 8,
                "manuscript_text": "gamma delta",
                "spoken_text": "gamma delta",
            }
        ]
    }

    issues = detect_pickup_restarts(manuscript_tokens, spoken_tokens, alignment)

    issue = next(issue for issue in issues if issue["type"] == "pickup_restart")
    assert issue["expected_text"] == "gamma delta"
    assert issue["start_ms"] == 6000
    assert issue["end_ms"] == 11500


def test_detect_alignment_issues_calls_pickup_restart_detection_once(monkeypatch):
    manuscript_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta eta theta iota kappa")
    spoken_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta gamma delta eta theta gamma delta iota kappa")
    alignment = {
        "matches": [
            {
                "op": "insert",
                "manuscript_start": 2,
                "manuscript_end": 2,
                "spoken_start": 6,
                "spoken_end": 8,
                "manuscript_text": "gamma delta",
                "spoken_text": "gamma delta",
            }
        ]
    }

    calls = {"count": 0}

    def fake_detect_pickup_restarts(*args, **kwargs):
        calls["count"] += 1
        return [{"type": "pickup_restart", "start_ms": 6000, "end_ms": 11500}]

    monkeypatch.setattr("app.services.detect.detect_pickup_restarts", fake_detect_pickup_restarts)

    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)

    assert calls["count"] == 1
    assert any(issue["type"] == "pickup_restart" for issue in issues)


def test_build_issue_records_defaults_low_confidence_status_to_pending():
    chapter = SimpleNamespace(id=7)
    manuscript_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta eta theta iota kappa")
    spoken_tokens = _timed_tokens("alpha beta gamma delta epsilon zeta gamma delta eta theta gamma delta iota kappa")
    alignment = {
        "matches": [
            {
                "op": "insert",
                "manuscript_start": 2,
                "manuscript_end": 2,
                "spoken_start": 6,
                "spoken_end": 8,
                "manuscript_text": "gamma delta",
                "spoken_text": "gamma delta",
            }
        ]
    }

    issue_records = build_issue_records(chapter, {}, manuscript_tokens, spoken_tokens, alignment)

    issue = next(issue for issue in issue_records if issue["type"] == "pickup_restart")
    assert issue["chapter_id"] == 7
    assert issue["status"] == "pending"
    assert issue["confidence"] == 0.72


def test_persist_issue_models_uses_confidence_based_default_status():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    issue_records = [
        {
            "type": "repetition",
            "start_ms": 100,
            "end_ms": 300,
            "confidence": 0.9,
            "expected_text": "alpha beta",
            "spoken_text": "alpha beta alpha beta",
            "context_before": "",
            "context_after": "",
        },
        {
            "type": "uncertain_alignment",
            "start_ms": 400,
            "end_ms": 500,
            "confidence": 0.58,
            "expected_text": "gamma",
            "spoken_text": "gamma",
            "context_before": "",
            "context_after": "",
        },
    ]

    with Session(engine) as session:
        persist_issue_models(session, chapter_id=11, issue_records=issue_records)
        issues = session.exec(select(Issue).order_by(Issue.id)).all()

    assert issues[0].status == "approved"
    assert issues[1].status == "pending"
