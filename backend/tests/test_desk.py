import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import (
    REASON_DESK,
    REASON_SPACING,
    DeskConfigError,
    desk_layout,
    find_violations,
    manhattan,
    place_candidates,
)
from app.api.halls import HallConfig, save_config
from app.api.seating import build_plan


# ---------- desk_layout：贴后墙与校验 ----------

def test_desk_flush_against_back_wall():
    # 5 行考室，1x2 桌 → 贴在第 4 行（最大行号）第 0–1 列
    blocked, rect = desk_layout(5, 6, 1, 2, 0)
    assert rect == {"row": 4, "col": 0, "rows": 1, "cols": 2}
    assert blocked == {(4, 0), (4, 1)}


def test_desk_multirow_extends_forward_from_back():
    # 2 行高的桌占据最后两行，仍是整块贴后墙，不可能悬在中部
    blocked, rect = desk_layout(5, 6, 2, 3, 1)
    assert rect == {"row": 3, "col": 1, "rows": 2, "cols": 3}
    assert blocked == {(3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (4, 3)}
    assert all(r >= 3 for r, _ in blocked)


def test_no_desk_matches_current_network():
    # 未配桌：无占格，与现网行为一致
    blocked, rect = desk_layout(5, 6, 0, 0, 0)
    assert blocked == set() and rect is None


@pytest.mark.parametrize("dr,dc,col", [(0, 2, 0), (2, 0, 0), (-1, 2, 0), (1, -1, 0), (1, 2, -1)])
def test_desk_non_positive_rejected(dr, dc, col):
    with pytest.raises(DeskConfigError):
        desk_layout(5, 6, dr, dc, col)


@pytest.mark.parametrize("dr,dc,col", [(6, 1, 0), (1, 7, 0), (1, 2, 5), (10, 10, 0)])
def test_desk_out_of_bounds_rejected(dr, dc, col):
    with pytest.raises(DeskConfigError):
        desk_layout(5, 6, dr, dc, col)


def test_desk_overlapping_front_rows_rejected():
    # 前排区为第 0..1 行；3 行高的桌顶边到第 2 行恰好不重叠
    assert desk_layout(5, 6, 3, 1, 0, front_rows=2)[1]["row"] == 2
    # 4 行高的桌顶边进入第 1 行 → 抢前排，拒绝（把桌放到第 0 行同理失败）
    with pytest.raises(DeskConfigError):
        desk_layout(5, 6, 4, 1, 0, front_rows=2)
    with pytest.raises(DeskConfigError):
        desk_layout(5, 6, 5, 1, 0, front_rows=1)


# ---------- 排座：占格、容量、未排原因 ----------

def test_seed_desk_cells_have_no_candidate():
    # 种子场景：桌区盖住最后一行第 0–1 列，这两格无人
    blocked, _ = desk_layout(5, 6, 1, 2, 0)
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 3)}
             for i in range(12)]
    assigns, _ = place_candidates(5, 6, 2, cands, blocked)
    positions = {(a.row, a.col) for a in assigns}
    assert positions.isdisjoint(blocked)
    assert (4, 0) not in positions and (4, 1) not in positions


def test_capacity_excludes_whole_rectangle():
    blocked, _ = desk_layout(5, 6, 1, 2, 0)
    assert len(blocked) == 2
    # 容量按去掉整块矩形对齐：30 - 2 = 28
    from app.services.seat_engine import plan_to_dict
    result = plan_to_dict([], [], [], 5, 6, blocked, None, 0)
    assert result["stats"]["capacity"] == 28
    assert result["stats"]["blocked"] == 2


def test_unplaced_due_to_desk_marked_desk_reason():
    # 2x2 考室被 1x2 后墙桌占掉最后一行 → 只剩 2 格；不同试卷第三人放不下，原因是桌区
    blocked, _ = desk_layout(2, 2, 1, 2, 0)
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + i} for i in range(3)]
    assigns, unplaced = place_candidates(2, 2, 1, cands, blocked)
    assert len(assigns) == 2 and len(unplaced) == 1
    assert unplaced[0]["reason"] == REASON_DESK
    assert "监考桌占格" in unplaced[0]["reason"]


def test_unplaced_due_to_spacing_marked_spacing_reason():
    # 无桌：2x2 只能坐下 2 个 min_dist=2 的考生，第三人未排系间距不足而非桌区
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1} for i in range(3)]
    assigns, unplaced = place_candidates(2, 2, 2, cands)
    assert len(unplaced) == 1
    assert unplaced[0]["reason"] == REASON_SPACING
    assert "监考桌" not in unplaced[0]["reason"]


def test_desk_blocked_cells_not_seated_full_room():
    blocked, _ = desk_layout(3, 3, 1, 1, 0)
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)}
             for i in range(20)]
    assigns, unplaced = place_candidates(3, 3, 1, cands, blocked)
    positions = {(a.row, a.col) for a in assigns}
    assert positions.isdisjoint(blocked)
    assert len(assigns) == 8  # 9 格去掉整块 1 格桌区


# ---------- 原有引擎能力不回退 ----------

def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3


def test_min_distance_placement():
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)} for i in range(4)]
    assigns, unplaced = place_candidates(4, 4, 2, cands)
    assert len(assigns) + len(unplaced) == 4
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 2


def test_violation_detection():
    from app.services.seat_engine import SeatAssign
    assigns = [SeatAssign(1, "A", "T1", 1, 0, 0), SeatAssign(2, "B", "T2", 1, 0, 1)]
    kinds = {v.kind for v in find_violations(2, 2, 2, assigns)}
    assert {"distance", "same_paper_adjacent"} <= kinds


# ---------- 配置保存：抢前排失败整体停在保存前；改尺寸与方案同成同败 ----------

@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    hall = Hall(code="H1", name="t", rows=5, cols=6, min_manhattan=2,
                front_rows=0, desk_rows=0, desk_cols=0, desk_col=0)
    db.add(hall)
    db.flush()
    for i in range(3):
        db.add(Candidate(hall_id=hall.id, name=f"C{i}", ticket_no=f"T{i}", paper_id=1 + i % 2))
    db.commit()
    yield db, hall.id
    db.close()


def test_save_config_rejects_desk_into_row_zero(db_session):
    db, hall_id = db_session
    # 先登记 1 行前排；5 行高的桌顶边到第 0 行 → 与前排抢行，保存必须失败
    with pytest.raises(Exception):
        save_config(hall_id, HallConfig(front_rows=1, desk_rows=5, desk_cols=1, desk_col=0), db)
    db.rollback()
    hall = db.get(Hall, hall_id)
    # 考室停在保存前：前排与桌配置都没落
    assert hall.front_rows == 0 and hall.desk_rows == 0
    assert db.scalars(select(SeatPlan)).all() == []


def test_save_config_rejects_out_of_bounds_atomically(db_session):
    db, hall_id = db_session
    with pytest.raises(Exception):
        save_config(hall_id, HallConfig(desk_rows=1, desk_cols=9, desk_col=0), db)
    db.rollback()
    hall = db.get(Hall, hall_id)
    assert hall.desk_cols == 0


def test_resize_rewrites_plan_together_and_keeps_history(db_session):
    db, hall_id = db_session
    # 先生效一条方案
    first = build_plan(db.get(Hall, hall_id), db)
    from app.api.seating import persist_plan
    persist_plan(hall_id, first, db)
    db.commit()
    before_count = len(db.scalars(select(SeatPlan)).all())

    # 改桌尺寸（已有有效方案）：尺寸与方案重写同成
    out = save_config(hall_id, HallConfig(desk_rows=1, desk_cols=2, desk_col=0), db)
    assert out["plan"] is not None
    hall = db.get(Hall, hall_id)
    assert hall.desk_cols == 2
    plans = db.scalars(select(SeatPlan).order_by(SeatPlan.id)).all()
    assert len(plans) == before_count + 1  # 历史方案不回刷，新增一条
    # 新方案已扣除整块桌区
    import json
    latest = json.loads(plans[-1].result_json)
    assert latest["stats"]["capacity"] == 5 * 6 - 2
    assert latest["desk"] == {"row": 4, "col": 0, "rows": 1, "cols": 2}
    # 旧方案保持原样（无桌、容量 30）
    old = json.loads(plans[0].result_json)
    assert old["stats"]["capacity"] == 30 and old.get("desk") is None


def test_save_config_without_plan_does_not_create_one(db_session):
    db, hall_id = db_session
    out = save_config(hall_id, HallConfig(desk_rows=1, desk_cols=2, desk_col=0), db)
    assert out["plan"] is None
    assert db.scalars(select(SeatPlan)).all() == []
