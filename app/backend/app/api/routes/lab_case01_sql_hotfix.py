"""Hotfix SQLAlchemy text() parsing for the Case 01 JSON literal.

SQLAlchemy treats ``:true`` inside a raw text() string as a bind parameter even
when it appears inside a PostgreSQL JSON string literal.  The Case 01 bootstrap
contains ``\"lab_specific_range_preferred\":true`` and therefore failed during
Render startup before the reference range row could be inserted.

This module is imported after ``lab_case01_safety`` and replaces that module's
``sql_text`` symbol with a tiny wrapper that escapes only the problematic token
before SQLAlchemy parses it.  SQLAlchemy removes the escape when compiling, so
PostgreSQL still receives valid JSON ``...:true``.
"""

from __future__ import annotations

from sqlalchemy import text as _sqlalchemy_text

from app.api.routes import lab_case01_safety


def _safe_sql_text(statement: str):
    if isinstance(statement, str):
        statement = statement.replace(
            '"lab_specific_range_preferred":true',
            '"lab_specific_range_preferred"\\:true',
        )
    return _sqlalchemy_text(statement)


lab_case01_safety.sql_text = _safe_sql_text
