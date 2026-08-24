from typing import Annotated

from pydantic import AfterValidator, Field

MIN_PASSWORD_LENGTH = 12
COMMON_PASSWORDS = {
    "123456789012",
    "password1234",
    "qwerty123456",
    "senha12345678",
}


def validate_password_strength(value: str) -> str:
    normalized = value.casefold().strip()
    if normalized in COMMON_PASSWORDS:
        raise ValueError("Escolha uma senha menos comum")
    if len(set(value)) < 6:
        raise ValueError("A senha tem pouca diversidade de caracteres")
    return value


StrongPassword = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=72),
    AfterValidator(validate_password_strength),
]
