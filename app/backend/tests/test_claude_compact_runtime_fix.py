from app.domain import claude_compact_runtime_fix as runtime_fix


def test_dedupe_preserves_order_and_removes_duplicates() -> None:
    assert runtime_fix._dedupe(["A", "B", "A", "C", "B"]) == ["A", "B", "C"]
