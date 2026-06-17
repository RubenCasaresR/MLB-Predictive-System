import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text

from api.database import get_async_engine
from etl.config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET

logger = logging.getLogger(__name__)

SECRET_KEY = JWT_SECRET
ALGORITHM = JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = JWT_ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "sub": str(to_encode.get("sub", ""))})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        raw = payload.get("sub")
        if raw is None:
            raise credentials_exception
        user_id = int(raw)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT user_id, username FROM users WHERE user_id = :uid"),
            {"uid": user_id},
        )
        row = result.fetchone()
    if row is None:
        raise credentials_exception
    return {"user_id": row[0], "username": row[1]}


@router.post("/register")
async def register(user: UserCreate):
    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        existing_result = await conn.execute(
            text("SELECT user_id FROM users WHERE username = :u"),
            {"u": user.username},
        )
        existing = existing_result.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")

    hashed = get_password_hash(user.password)
    async with async_engine.begin() as conn:
        insert_result = await conn.execute(
            text("INSERT INTO users (username, hashed_password) VALUES (:u, :h) RETURNING user_id"),
            {"u": user.username, "h": hashed},
        )
        user_id = insert_result.fetchone()[0]

    token = create_access_token(data={"sub": user_id})
    return TokenResponse(access_token=token, user_id=user_id)


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT user_id, username, hashed_password FROM users WHERE username = :u"),
            {"u": form_data.username},
        )
        row = result.fetchone()

    if not row or not verify_password(form_data.password, row[2]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": row[0]})
    return TokenResponse(access_token=token, user_id=row[0])
