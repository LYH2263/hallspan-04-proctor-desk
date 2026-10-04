"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent.

监考桌占格：监考桌是一块贴后墙（最大行号那一侧）的矩形，矩形内每一格都不落考生。
桌区从前向后最多延伸到「前排区」之前；越界、宽高非正、与前排行数区间重叠均为非法配置。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# 未排原因：桌区占格 / 间距（含同卷相邻）约束
REASON_DESK = "监考桌占格"
REASON_SPACING = "间距不足"


class DeskConfigError(ValueError):
    """监考桌配置非法（宽高非正 / 越界 / 与前排区抢行）。"""


@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int


@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def desk_layout(
    rows: int,
    cols: int,
    desk_rows: int,
    desk_cols: int,
    desk_col: int,
    front_rows: int = 0,
) -> tuple[set[tuple[int, int]], dict | None]:
    """计算贴后墙监考桌的占格集合与矩形描述。

    贴后墙：矩形底边固定在第 rows-1 行，顶边为 rows-desk_rows，不存在任意纵向放置。
    未配桌（desk_rows/desk_cols 均为 0）返回空集，行为与现网一致。
    宽高非正、越界、与前排行数区间重叠时抛 DeskConfigError。
    """
    if not (0 <= front_rows <= rows):
        raise DeskConfigError("前排行数区间越出考室边界")
    if desk_rows == 0 and desk_cols == 0:
        return set(), None
    if desk_rows <= 0 or desk_cols <= 0 or desk_col < 0:
        raise DeskConfigError("监考桌宽高必须为正整数，未配桌时宽高均填 0")
    if desk_rows > rows or desk_col + desk_cols > cols:
        raise DeskConfigError("监考桌越出考室边界")
    top = rows - desk_rows
    # 前排区为第 0 .. front_rows-1 行；桌区顶行进入该区间即抢行
    if top < front_rows:
        raise DeskConfigError("监考桌占用行与前排行数区间重叠，桌区不得伸入前排区")
    cells = {
        (r, c)
        for r in range(top, rows)
        for c in range(desk_col, desk_col + desk_cols)
    }
    rect = {"row": top, "col": desk_col, "rows": desk_rows, "cols": desk_cols}
    return cells, rect


def _seat_ok(
    r: int,
    c: int,
    occupied: dict[tuple[int, int], SeatAssign],
    min_dist: int,
    paper_id: int,
    rows: int,
    cols: int,
) -> bool:
    for pos, other in occupied.items():
        if manhattan((r, c), pos) < min_dist:
            return False
        if other.paper_id == paper_id and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
            return False
    for nr, nc in neighbors4(r, c, rows, cols):
        if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == paper_id:
            return False
    return True


def place_candidates(
    rows: int,
    cols: int,
    min_dist: int,
    candidates: list[dict],
    blocked: set[tuple[int, int]] | None = None,
) -> tuple[list[SeatAssign], list[dict]]:
    """Greedy: try seats row-major; accept if manhattan >= min_dist to all placed AND no same paper 4-neigh.

    blocked 为监考桌占格：整块矩形都不参与排座。因桌区放不下的考生只进未排，
    原因标注「监考桌占格」；桌外也无处可坐时才标注「间距不足」。
    """
    blocked = blocked or set()
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed_pos: tuple[int, int] | None = None
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied or (r, c) in blocked:
                    continue
                if _seat_ok(r, c, occupied, min_dist, cand["paper_id"], rows, cols):
                    placed_pos = (r, c)
                    break
            if placed_pos:
                break
        if placed_pos is None:
            # 反事实：若去掉监考桌，该考生能否坐进桌区某格？能则未排系桌区占格所致。
            reason = REASON_SPACING
            for r, c in blocked:
                if _seat_ok(r, c, occupied, min_dist, cand["paper_id"], rows, cols):
                    reason = REASON_DESK
                    break
            unplaced.append({**cand, "reason": reason})
            continue
        r, c = placed_pos
        occupied[(r, c)] = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
    return list(occupied.values()), unplaced


def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    viols: list[Violation] = []
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols


def plan_to_dict(
    assigns: list[SeatAssign],
    unplaced: list[dict],
    viols: list[Violation],
    rows: int,
    cols: int,
    blocked: set[tuple[int, int]] | None = None,
    desk: dict | None = None,
    front_rows: int = 0,
) -> dict:
    blocked = blocked or set()
    return {
        "rows": rows,
        "cols": cols,
        "front_rows": front_rows,
        "desk": desk,
        "blocked": sorted((r, c) for r, c in blocked),
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            # 可坐容量按去掉整块监考桌矩形后对齐
            "capacity": rows * cols - len(blocked),
            "blocked": len(blocked),
        },
    }
