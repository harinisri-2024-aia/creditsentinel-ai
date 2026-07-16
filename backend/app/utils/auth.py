import os
import datetime
from typing import Optional, List
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import get_db, User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    email = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory for role-based access control.

    Usage:
        @router.post("/datasets/upload")
        def upload(..., current_user: User = Depends(require_role("admin", "data_scientist"))):
            ...

    Admins implicitly pass every role check so a single admin account can
    always manage the platform end-to-end.
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == "admin" or current_user.role in allowed_roles:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires one of the following roles: {', '.join(allowed_roles)}. "
                   f"Your role is '{current_user.role}'.",
        )

    return _dependency


# Convenience role-check dependencies for the permission matrix requested:
#   Data Scientist -> train models, upload datasets
#   Auditor        -> view fairness reports, view logs
#   Loan Officer   -> view applicants/predictions, request predictions
#   Admin          -> manage users, approve deployment, configure thresholds
can_train_models = require_role("data_scientist")
can_upload_datasets = require_role("data_scientist")
can_view_fairness_reports = require_role("data_scientist", "auditor", "admin")
can_approve_deployment = require_role("admin")
can_manage_users = require_role("admin")
can_configure_thresholds = require_role("admin")
can_view_applicants = require_role("loan_officer", "data_scientist", "auditor", "admin")
