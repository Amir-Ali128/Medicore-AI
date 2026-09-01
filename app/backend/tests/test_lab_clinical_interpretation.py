from app.domain.lab_clinical_interpretation_runtime import _lookup


def test_alt_high_has_liver_associations() -> None:
    interpretation, causes = _lookup("ALT (Alanin Aminotransferaz)", "high")

    assert interpretation is not None
    assert "karaciğer" in interpretation.lower()
    assert any("hepatit" in cause.lower() for cause in causes)


def test_hemoglobin_low_has_anemia_associations() -> None:
    interpretation, causes = _lookup("Hemoglobin (HGB)", "low")

    assert interpretation is not None
    assert "anemi" in interpretation.lower()
    assert any("demir" in cause.lower() for cause in causes)


def test_unknown_parameter_does_not_invent_disease() -> None:
    interpretation, causes = _lookup("Bilinmeyen Parametre XYZ", "high")

    assert interpretation is None
    assert causes == []
