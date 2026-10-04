import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import (
    DeskConfigError,
    desk_layout,
    find_violations,
    place_candidates,
    plan_to_dict,
)

router = APIRouter(prefix="/seating", tags=["seating"])


def build_plan(hall: Hall, db: Session) -> dict:
    """按考室当前配置（含监考桌占格）重排，返回不落库的结果 dict。"""
    blocked, desk = desk_layout(
        hall.rows, hall.cols, hall.desk_rows, hall.desk_cols, hall.desk_col, hall.front_rows
    )
    cands = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall.id)).all()
    ]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands, blocked)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(
        assigns, unplaced, viols, hall.rows, hall.cols, blocked, desk, hall.front_rows
    )
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    return result


def persist_plan(hall_id: int, result: dict, db: Session) -> SeatPlan:
    plan = SeatPlan(
        hall_id=hall_id,
        created_at=datetime.utcnow(),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(plan)
    db.flush()
    return plan


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    try:
        result = build_plan(hall, db)
    except DeskConfigError as exc:
        raise HTTPException(400, str(exc))
    plan = persist_plan(hall_id, result, db)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, **result}


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    plan = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).first()
    if not plan:
        return run_seating(hall_id=hall_id, db=db)
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, "violations": data.get("violations", []), "unplaced": data.get("unplaced", [])}


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
