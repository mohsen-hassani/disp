import pytest

from disp.core.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)

# Case 1: hash/verify round-trip; malformed hash returns False.


def test_hash_verify_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password entirely", hashed) is False


def test_verify_password_with_malformed_hash_returns_false() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


# Case 2: policy rejects <12 chars, >128 chars, password==email, common-list password.


def test_policy_rejects_too_short() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("short1", email="user@example.com")


def test_policy_rejects_too_long() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("a" * 129, email="user@example.com")


def test_policy_rejects_password_equal_to_email() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("User@Example.com", email="user@example.com")


def test_policy_rejects_common_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("password1", email="user@example.com")


def test_policy_accepts_a_reasonable_password() -> None:
    validate_password_policy("a-perfectly-cromulent-password-123", email="user@example.com")
