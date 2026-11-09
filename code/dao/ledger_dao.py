"""账本表数据访问（对应类图：账本）。"""

from typing import Optional

from dao.db import get_connection
from model.ledger import Ledger


def _row_to_ledger(row: dict) -> Ledger:
    """把查询结果行转换为 Ledger 实体。"""
    return Ledger(
        ledger_id=row["ledger_id"],
        name=row["name"],
        template_id=row["template_id"],
        effective_time=row["effective_time"],
        settling=bool(row["settling"]),
    )


def add(name: str, template_id: int) -> int:
    """创建账本（生效时间取数据库默认的当前时间），返回账本 ID。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ledger (name, template_id) VALUES (%s, %s)",
                (name, template_id),
            )
            return cur.lastrowid


def get_by_id(ledger_id: int) -> Optional[Ledger]:
    """按账本 ID 查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ledger WHERE ledger_id = %s", (ledger_id,)
            )
            row = cur.fetchone()
            return _row_to_ledger(row) if row else None


def set_settling(ledger_id: int, settling: bool) -> None:
    """设置账本结算进行中标志（REQ-012：结算期间拒绝一切操作）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger SET settling = %s WHERE ledger_id = %s",
                (1 if settling else 0, ledger_id),
            )


def is_settling(ledger_id: int) -> bool:
    """查询账本是否处于结算进行中（REQ-012）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT settling FROM ledger WHERE ledger_id = %s",
                (ledger_id,),
            )
            row = cur.fetchone()
            return bool(row["settling"]) if row else False


def list_by_user(user_id: int) -> list[Ledger]:
    """查询某用户加入的全部账本（经成员关系关联）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT l.* FROM ledger l "
                "JOIN membership m ON l.ledger_id = m.ledger_id "
                "WHERE m.user_id = %s ORDER BY l.ledger_id",
                (user_id,),
            )
            return [_row_to_ledger(row) for row in cur.fetchall()]
