from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Hall, SeatPlan
from app.services.seat_engine import DeskConfigError, desk_layout
from app.api.seating import build_plan, persist_plan

router = APIRouter(prefix="/halls", tags=["halls"])


def hall_dict(r: Hall) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "rows": r.rows,
        "cols": r.cols,
        "min_manhattan": r.min_manhattan,
        "front_rows": r.front_rows,
        "desk_rows": r.desk_rows,
        "desk_cols": r.desk_cols,
        "desk_col": r.desk_col,
    }


class HallConfig(BaseModel):
    rows: int | None = None
    cols: int | None = None
    min_manhattan: int | None = None
    front_rows: int | None = None
    desk_rows: int | None = None
    desk_cols: int | None = None
    desk_col: int | None = None


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [hall_dict(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


@router.put("/{hall_id}/config")
def save_config(hall_id: int, body: HallConfig, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")

    rows = body.rows if body.rows is not None else hall.rows
    cols = body.cols if body.cols is not None else hall.cols
    min_dist = body.min_manhattan if body.min_manhattan is not None else hall.min_manhattan
    front_rows = body.front_rows if body.front_rows is not None else hall.front_rows
    desk_rows = body.desk_rows if body.desk_rows is not None else hall.desk_rows
    desk_cols = body.desk_cols if body.desk_cols is not None else hall.desk_cols
    desk_col = body.desk_col if body.desk_col is not None else hall.desk_col

    if rows <= 0 or cols <= 0 or min_dist <= 0 or front_rows < 0:
        raise HTTPException(400, "行数、列数、最小间距必须为正整数，前排行数不得为负")

    # 先校验桌区：宽高非正 / 越界 / 与前排区抢行 → 直接失败，考室与方案都停在保存前
    try:
        blocked, desk = desk_layout(rows, cols, desk_rows, desk_cols, desk_col, front_rows)
    except DeskConfigError as exc:
        raise HTTPException(400, str(exc))

    has_plan = (
        db.scalar(select(SeatPlan.id).where(SeatPlan.hall_id == hall_id).limit(1)) is not None
    )

    # 配置写入与方案重写同处一个事务：同成同败，失败整体回滚
    hall.rows, hall.cols, hall.min_manhattan = rows, cols, min_dist
    hall.front_rows, hall.desk_rows, hall.desk_cols, hall.desk_col = (
        front_rows, desk_rows, desk_cols, desk_col,
    )

    new_plan = None
    if has_plan:
        # 历史方案不回刷：按新配置重排并另存为一条新方案，旧方案原样保留
        result = build_plan(hall, db)
        new_plan = persist_plan(hall_id, result, db)
        result_out = {"id": new_plan.id, **result}
    else:
        result_out = None

    db.commit()
    return {"hall": hall_dict(hall), "plan": result_out}
