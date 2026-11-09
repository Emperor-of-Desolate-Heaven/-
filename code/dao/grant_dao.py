"""日志访问授权表数据访问（对应类图：日志访问授权）。"""

from typing import Optional

from dao.db import get_connection
from model.log_access_grant import LogAccessGrant


def _row_to_grant(row: dict) -> LogAccessGrant:
    """把查询结果行转换为 LogAccessGrant 实体。"""
    return LogAccessGrant(
        grant_id=row["grant_id"],
        membership_id=row["membership_id"],
        grant_admin_id=row["grant_admin_id"],
        grant_time=row["grant_time"],
        used=bool(row["used"]),
    )


def add(membership_id: int, grant_admin_id: int) -> int:
    """新增一条日志访问授权（REQ-015）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO log_access_grant "
                "(membership_id, grant_admin_id) VALUES (%s, %s)",
                (membership_id, grant_admin_id),
            )
            return cur.lastrowid


def get_valid(membership_id: int) -> Optional[LogAccessGrant]:
    """查询尚未使用的有效授权，没有返回 None（一次有效）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant "
                "WHERE membership_id = %s AND used = 0 "
                "ORDER BY grant_id DESC LIMIT 1",
                (membership_id,),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def get_latest(membership_id: int) -> Optional[LogAccessGrant]:
    """查询最近一次授权（用于"一天后重新申请"判断）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant WHERE membership_id = %s "
                "ORDER BY grant_id DESC LIMIT 1",
                (membership_id,),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def mark_used(grant_id: int) -> None:
    """把授权标记为已使用（一次有效，REQ-015）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE log_access_grant SET used = 1 WHERE grant_id = %s",
                (grant_id,),
            )
