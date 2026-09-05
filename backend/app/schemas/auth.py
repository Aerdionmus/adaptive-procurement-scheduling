import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import UserRole

# Deliberately not pydantic's EmailStr: that requires the extra
# `email-validator` dependency for one field. A simple, well-understood
# regex is sufficient here since this is a login identifier, not a field
# we need to send mail to.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ADMIN accounts are intentionally not self-registerable: allowing a caller
# to POST their way into an admin role would defeat the entire RBAC model.
# Admin users are provisioned out-of-band (seed data / an existing admin),
# not through this public endpoint.
SELF_REGISTERABLE_ROLES = (UserRole.FARMER, UserRole.CENTRE_STAFF)


class UserRegister(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    farmer_id: int | None = Field(
        default=None, description="Required, and only valid, when role=FARMER."
    )
    centre_id: int | None = Field(
        default=None, description="Required, and only valid, when role=CENTRE_STAFF."
    )

    @field_validator("email")
    @classmethod
    def _email_must_look_like_an_email(cls, value: str) -> str:
        if not _EMAIL_PATTERN.match(value):
            raise ValueError("Must be a valid email address")
        return value.lower()

    @field_validator("role")
    @classmethod
    def _role_must_be_self_registerable(cls, value: UserRole) -> UserRole:
        if value not in SELF_REGISTERABLE_ROLES:
            raise ValueError("This role cannot be self-registered")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: UserRole
    farmer_id: int | None
    centre_id: int | None
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
