import re

from pydantic import BaseModel, Field, field_validator


class EmailModel(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("invalid email address")
        return normalized


class LoginInput(EmailModel):
    password: str = Field(min_length=1, max_length=1024)


class InvitationInput(EmailModel):
    pass


class AcceptInvitationInput(BaseModel):
    token: str = Field(min_length=30, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class ApiKeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned
