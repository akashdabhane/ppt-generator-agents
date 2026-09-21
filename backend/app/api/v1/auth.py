import hashlib
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from jose import jwt

from app.core.config import settings
from app.api.v1.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["Auth"])


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{pwd_hash.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt_hex, hash_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return pwd_hash.hex() == hash_hex
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    result = db.execute(select(User).where(User.email == user_in.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    hashed_pw = hash_password(user_in.password)
    user = User(
        email=user_in.email,
        hashed_password=hashed_pw,
        full_name=user_in.full_name
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    result = db.execute(select(User).where(User.email == user_in.email))
    user = result.scalars().first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    token = create_access_token({"sub": user.id})
    return Token(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
