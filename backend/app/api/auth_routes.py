from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db, User, AuditLog, USER_ROLES
from app.utils.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    company: str = ""
    password: str
    # Role-Based Authentication (Feature 6). Defaults to "data_scientist" so
    # existing registration flows that don't send a role keep working exactly
    # as before. Admin accounts should be assigned via /api/admin/users/{id}/role
    # by an existing admin rather than self-selected at signup in production,
    # but self-selection is left open here to keep first-run setup simple.
    role: str = "data_scientist"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    company: str
    role: str

    class Config:
        from_attributes = True


@router.get("/roles")
def list_roles():
    return {"roles": USER_ROLES}


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    role = payload.role if payload.role in USER_ROLES else "data_scientist"

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        company=payload.company,
        hashed_password=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(AuditLog(user_id=user.id, action="user_registered", details=f"User {user.email} registered with role '{role}'"))
    db.commit()

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": user.email})

    db.add(AuditLog(user_id=user.id, action="user_login", details=f"User {user.email} logged in"))
    db.commit()

    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
