from pydantic import ValidationError
import pytest

from app.api.routes.auth import LoginRequest, RegisterRequest


def test_register_normalizes_nickname_to_lowercase() -> None:
    payload = RegisterRequest(nickname="  NightFox_27  ", password="secret12")
    assert payload.nickname == "nightfox_27"


def test_register_rejects_whitespace_in_nickname() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(nickname="night fox", password="secret12")


def test_login_carries_account_type() -> None:
    payload = LoginRequest(
        nickname="doctor",
        password="demo123",
        account_type="institutional",
    )
    assert payload.nickname == "doctor"
    assert payload.account_type == "institutional"


def test_public_registration_has_no_role_or_identity_fields() -> None:
    fields = set(RegisterRequest.model_fields)
    assert fields == {"nickname", "password"}
