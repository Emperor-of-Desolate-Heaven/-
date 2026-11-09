"""成员关系表数据访问（对应类图：成员关系）。"""

from typing import Optional

from dao.db import get_connection
from model.enums import Role
from model.membership import Membership


def _row_to_membership(row: dict) -> Membership:
    """把查询结果行转换为 Membership 实体。"""
    return Membership(
        membership_id=row["membership_id"],
        ledger_id=row["ledger_id"],
        user_id=row["user_id"],
        role=Role(row["role"]),
        join_time=row["join_time"],
        visibility_on=bool(row["visibility_on"]),
    )


def add(ledger_id: int, user_id: int, role: Role = Role.MEMBER) -> int:
    """新增成员关系，返回成员关系 ID。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO membership (ledger_id, user_id, role) "
                "VALUES (%s, %s, %s)",
                (ledger_id, user_id, role.value),
            )
            return cur.lastrowid


def get(ledger_id: int, user_id: int) -> Optional[Membership]:
    """查询某用户在某账本中的成员关系，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM membership WHERE ledger_id = %s AND user_id = %s",
                (ledger_id, user_id),
            )
            row = cur.fetchone()
            return _row_to_membership(row) if row else None


def get_by_id(membership_id: int) -> Optional[Membership]:
    """按成员关系 ID 查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM membership WHERE membership_id = %s",
                (membership_id,),
            )
            row = cur.fetchone()
            return _row_to_membership(row) if row else None


def list_by_ledger(ledger_id: int) -> list[Membership]:
    """查询账本的全部成员关系。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM membership WHERE ledger_id = %s "
                "ORDER BY membership_id",
                (ledger_id,),
            )
            return [_row_to_membership(row) for row in cur.fetchall()]


def update_role(membership_id: int, role: Role) -> None:
    """修改成员角色（超管专用，REQ-001）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE membership SET role = %s WHERE membership_id = %s",
                (role.value, membership_id),
            )


def set_visibility(membership_id: int, visibility_on: bool) -> None:
    """设置记录可见性（REQ-022）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE membership SET visibility_on = %s "
                "WHERE membership_id = %s",
                (1 if visibility_on else 0, membership_id),
            )


def remove(membership_id: int) -> None:
    """移除成员关系（REQ-003）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM membership WHERE membership_id = %s",
                (membership_id,),
            )


def count_by_role(ledger_id: int, role: Role) -> int:
    """统计账本内某角色的成员数量（用于"一个账本只能有一个超级管理员"校验）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM membership "
                "WHERE ledger_id = %s AND role = %s",
                (ledger_id, role.value),
            )
            return cur.fetchone()["cnt"]
