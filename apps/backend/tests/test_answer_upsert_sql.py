from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from api.candidates.domain.entities import Answer
from api.candidates.infrastructure.repository import build_upsert_statement


def sample_answer() -> Answer:
    return Answer(
        id=1,
        candidate_id=42,
        question_id=7,
        answer_type="text",
        text="hello",
        audio_key=None,
        content_hash="abc123",
        version=1,
        external_ref=None,
        submitted_at=datetime.now(UTC),
    )


def test_upsert_uses_on_conflict_with_content_hash_guard() -> None:
    stmt = build_upsert_statement(sample_answer())
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (candidate_id, question_id)" in sql
    assert "answers.content_hash" in sql and "excluded.content_hash" in sql
    assert "version = answers.version + 1" in sql


def test_upsert_updates_answer_type() -> None:
    stmt = build_upsert_statement(sample_answer())
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "DO UPDATE SET answer_type = " in sql
