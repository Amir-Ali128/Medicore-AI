from app.domain.ultrasound_result_only_runtime import analyze_with_ultrasound_result_only


def test_ultrasound_uses_only_explicit_result_section() -> None:
    text = """
    ABDOMEN ULTRASONOGRAFİ
    BULGULAR:
    Karaciğer parankimi ayrıntılı bulgu metni.
    Safra kesesi duvar kalınlığı normaldir.
    SONUÇ:
    Safra kesesinde taş ile uyumlu görünüm izlenmiştir.
    """

    result = analyze_with_ultrasound_result_only(text)

    assert result["impression"] == "Safra kesesinde taş ile uyumlu görünüm izlenmiştir."
    assert "Safra kesesinde taş" in result["summary"]
    assert "Karaciğer parankimi" not in result["summary"]
    assert result["safety_version"] == "ultrasound-result-only-v1"


def test_ultrasound_does_not_fallback_when_result_section_missing() -> None:
    text = """
    ABDOMEN ULTRASONOGRAFİ
    BULGULAR:
    Karaciğer parankimi homojendir.
    """

    result = analyze_with_ultrasound_result_only(text)

    assert result["impression"] is None
    assert result["findings"] == []
    assert "Sonuç/İzlenim" in result["summary"]
