import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

# The 100 most common passwords (publicly known, widely used for policy checks).
# Compared case-insensitively against user-supplied passwords.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456",
        "123456789",
        "qwerty",
        "password",
        "12345",
        "qwerty123",
        "1q2w3e",
        "12345678",
        "111111",
        "1234567890",
        "1234567",
        "123123",
        "abc123",
        "1234",
        "password1",
        "iloveyou",
        "1q2w3e4r",
        "000000",
        "qwertyuiop",
        "dragon",
        "monkey",
        "letmein",
        "login",
        "princess",
        "qwertyui",
        "solo",
        "passw0rd",
        "starwars",
        "welcome",
        "121212",
        "admin",
        "654321",
        "555555",
        "lovely",
        "7777777",
        "888888",
        "mynoob",
        "football",
        "baseball",
        "sunshine",
        "master",
        "shadow",
        "superman",
        "trustno1",
        "hello",
        "freedom",
        "whatever",
        "qazwsx",
        "flower",
        "michael",
        "jennifer",
        "jordan",
        "hunter",
        "hunter2",
        "buster",
        "soccer",
        "harley",
        "ranger",
        "daniel",
        "thomas",
        "tigger",
        "robert",
        "andrew",
        "joshua",
        "matthew",
        "charlie",
        "martin",
        "andrea",
        "junior",
        "computer",
        "batman",
        "cookie",
        "summer",
        "george",
        "amanda",
        "jessica",
        "pepper",
        "yellow",
        "purple",
        "orange",
        "secret",
        "ginger",
        "nicole",
        "chelsea",
        "biteme",
        "matrix",
        "maggie",
        "jasmine",
        "taylor",
        "midnight",
        "eagle1",
        "cowboy",
        "silver",
        "richard",
        "access",
        "yankees",
        "testing",
        "changeme",
        "letmein1",
        "passw0rd1",
    }
)

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class PasswordPolicyError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(plain, hashed)
    except Exception:
        return False


def validate_password_policy(plain: str, *, email: str) -> None:
    if len(plain) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(plain) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if plain.casefold() == email.casefold():
        raise PasswordPolicyError("Password must not be the same as your email address.")
    if plain.casefold() in COMMON_PASSWORDS:
        raise PasswordPolicyError("This password is too common. Please choose another one.")


# Used to equalise login timing between "user not found" and "wrong password".
DUMMY_HASH: str = hash_password(secrets.token_urlsafe(32))
