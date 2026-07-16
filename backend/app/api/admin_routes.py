from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, User, ModelVersion, AuditLog, USER_ROLES
from app.utils.auth import get_current_user, can_manage_users, can_approve_deployment, can_configure_thresholds
from app.services import threshold_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RoleUpdateRequest(BaseModel):
    role: str


class ThresholdUpdateRequest(BaseModel):
    user_id: int
    disparate_impact_min: float
    equal_opportunity_max: float


class DeploymentApprovalRequest(BaseModel):
    model_id: int
    approve: bool
    note: str = ""


@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(can_manage_users)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "company": u.company,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_users),
):
    if payload.role not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(USER_ROLES)}")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = payload.role
    db.commit()

    db.add(AuditLog(
        user_id=current_user.id,
        action="user_role_updated",
        details=f"Admin {current_user.email} changed {user.email}'s role from '{old_role}' to '{payload.role}'.",
    ))
    db.commit()

    return {"id": user.id, "email": user.email, "role": user.role}


@router.get("/thresholds/{user_id}")
def get_thresholds(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(can_configure_thresholds)):
    return threshold_service.get_thresholds_for_user(db, user_id)


@router.put("/thresholds")
def update_thresholds(
    payload: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_configure_thresholds),
):
    """Configurable Fairness Thresholds (Feature 7) — Admin only."""
    if not (0 < payload.disparate_impact_min <= 1):
        raise HTTPException(status_code=400, detail="disparate_impact_min must be between 0 and 1")
    if not (0 <= payload.equal_opportunity_max <= 1):
        raise HTTPException(status_code=400, detail="equal_opportunity_max must be between 0 and 1")

    row = threshold_service.upsert_thresholds(
        db, payload.user_id, payload.disparate_impact_min, payload.equal_opportunity_max, current_user.id
    )

    db.add(AuditLog(
        user_id=current_user.id,
        action="fairness_thresholds_updated",
        details=(
            f"Admin {current_user.email} set fairness thresholds for user_id={payload.user_id}: "
            f"disparate_impact_min={payload.disparate_impact_min}, equal_opportunity_max={payload.equal_opportunity_max}"
        ),
    ))
    db.commit()

    return {
        "user_id": row.user_id,
        "disparate_impact_min": row.disparate_impact_min,
        "equal_opportunity_max": row.equal_opportunity_max,
    }


@router.post("/approve-deployment")
def approve_deployment(
    payload: DeploymentApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_approve_deployment),
):
    """
    Admin sign-off step. Even if a model already passed the automated
    performance + fairness gates, an Admin can still require an explicit
    human approval before a model is marked 'production', or can veto/roll
    back a model that automation approved.
    """
    model_version = db.query(ModelVersion).filter(ModelVersion.id == payload.model_id).first()
    if not model_version:
        raise HTTPException(status_code=404, detail="Model not found")

    if payload.approve:
        model_version.status = "production"
        model_version.governance_decision = "approved"
        action_detail = f"Admin {current_user.email} approved deployment of model {payload.model_id}."
    else:
        model_version.status = "rejected"
        model_version.governance_decision = "rejected"
        action_detail = f"Admin {current_user.email} rejected deployment of model {payload.model_id}."
    if payload.note:
        action_detail += f" Note: {payload.note}"
    db.commit()

    db.add(AuditLog(user_id=current_user.id, action="admin_deployment_decision", details=action_detail))
    db.commit()

    return {"model_id": model_version.id, "status": model_version.status, "governance_decision": model_version.governance_decision}
