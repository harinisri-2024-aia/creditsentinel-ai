from sqlalchemy.orm import Session

from app.database import FairnessThreshold
from app.services.fairness_service import DEFAULT_FAIRNESS_THRESHOLDS


def get_thresholds_for_user(db: Session, user_id: int) -> dict:
    """
    Returns the effective fairness thresholds for a given user: their own
    override row if one exists, otherwise the global defaults.
    """
    row = db.query(FairnessThreshold).filter(FairnessThreshold.user_id == user_id).first()
    if row:
        return {
            "disparate_impact_min": row.disparate_impact_min,
            "equal_opportunity_max": row.equal_opportunity_max,
        }
    return dict(DEFAULT_FAIRNESS_THRESHOLDS)


def upsert_thresholds(db: Session, user_id: int, disparate_impact_min: float,
                       equal_opportunity_max: float, updated_by: int) -> FairnessThreshold:
    row = db.query(FairnessThreshold).filter(FairnessThreshold.user_id == user_id).first()
    if row:
        row.disparate_impact_min = disparate_impact_min
        row.equal_opportunity_max = equal_opportunity_max
        row.updated_by = updated_by
    else:
        row = FairnessThreshold(
            user_id=user_id,
            disparate_impact_min=disparate_impact_min,
            equal_opportunity_max=equal_opportunity_max,
            updated_by=updated_by,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row
