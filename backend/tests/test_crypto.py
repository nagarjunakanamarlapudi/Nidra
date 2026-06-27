import pytest

from pragya_assistant.crypto import decrypt_secret, encrypt_secret

KEY = "a-test-secret-key-long-enough"


def test_round_trip() -> None:
    token = encrypt_secret("access-sandbox-123", KEY)
    assert token != "access-sandbox-123"  # actually encrypted
    assert decrypt_secret(token, KEY) == "access-sandbox-123"


def test_wrong_key_fails() -> None:
    token = encrypt_secret("secret", KEY)
    with pytest.raises(Exception):  # noqa: B017
        decrypt_secret(token, "a-different-secret-key-entirely")
