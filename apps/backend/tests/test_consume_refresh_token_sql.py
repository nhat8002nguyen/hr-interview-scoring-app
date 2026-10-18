from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from api.auth.infrastructure.refresh_token_storage import consume_refresh_token


def test_consume_refresh_token_is_atomic_delete_returning() -> None:
    stmt = consume_refresh_token("jti-1", datetime.now(UTC))
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "DELETE" in sql and "refresh_tokens.token_id" in sql and "RETURNING" in sql
