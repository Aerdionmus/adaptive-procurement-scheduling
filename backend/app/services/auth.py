from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Farmer, ProcurementCentre, User, UserRole
from app.repositories import users as user_repository
from app.schemas.auth import UserRegister


@dataclass
class AuthError(Exception):
    detail: str
    status_code: int


def register_user(session: Session, data: UserRegister) -> User:
    if user_repository.get_user_by_email(session, data.email) is not None:
        raise AuthError("An account with this email already exists", 409)

    if data.role == UserRole.FARMER:
        if data.farmer_id is None:
            raise AuthError("farmer_id is required when registering as FARMER", 422)
        if data.centre_id is not None:
            raise AuthError("centre_id is not valid when registering as FARMER", 422)
        farmer = session.get(Farmer, data.farmer_id)
        if farmer is None:
            raise AuthError("Farmer not found", 404)
        if user_repository.get_user_by_farmer_id(session, data.farmer_id) is not None:
            raise AuthError("This farmer already has an account", 409)
        centre_id = None
        farmer_id = data.farmer_id
    else:  # UserRole.CENTRE_STAFF (ADMIN is rejected by the schema itself)
        if data.centre_id is None:
            raise AuthError("centre_id is required when registering as CENTRE_STAFF", 422)
        if data.farmer_id is not None:
            raise AuthError("farmer_id is not valid when registering as CENTRE_STAFF", 422)
        centre = session.get(ProcurementCentre, data.centre_id)
        if centre is None:
            raise AuthError("Procurement centre not found", 404)
        centre_id = data.centre_id
        farmer_id = None

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        farmer_id=farmer_id,
        centre_id=centre_id,
    )
    return user_repository.create_user(session, user)


def authenticate_user(session: Session, email: str, password: str) -> User:
    user = user_repository.get_user_by_email(session, email.lower())
    # Deliberately identical error for "no such user" and "wrong password":
    # distinguishing them would let a caller enumerate registered emails.
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise AuthError("Incorrect email or password", 401)
    return user
