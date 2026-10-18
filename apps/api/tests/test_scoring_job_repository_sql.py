from datetime import UTC, datetime

from api.scoring.infrastructure.repository import (
    build_claim_statement,
    build_load_scoring_input_statement,
    build_record_failure_statement,
)
from sqlalchemy.dialects import postgresql


def test_claim_uses_skip_locked() -> None:
    sql = str(build_claim_statement().compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "status = 'queued'" in sql
    assert "claimed_at IS NULL" in sql


def test_record_failure_transitions() -> None:
    stmt = build_record_failure_statement(1, "boom", datetime.now(UTC), 3)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "CASE" in sql
    assert "attempt_count" in sql
    assert "failed" in sql
    assert "queued" in sql


def test_load_scoring_input_joins() -> None:
    sql = str(build_load_scoring_input_statement(1).compile(dialect=postgresql.dialect()))
    assert "answers" in sql
    assert "questions" in sql
    assert "JOIN questions ON answers.question_id = questions.id" in sql
    assert "answers.text" in sql
    assert "questions.prompt" in sql
