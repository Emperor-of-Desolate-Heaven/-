"""日志访问授权表数据访问（对应类图：日志访问授权）。

流程（REQ-015）：申请（待审批）→ 管理员审批（已批准/已驳回）
→ 成员使用一次（used=1 作废）→ 一天后才能重新申请。
status 列为实现补充设计（申请中间态，与 membership.status 同一模式）。
"""

from typing import Optional

from dao.db import get_connection
from model.enums import GrantStatus
from model.log_access_grant import LogAccessGrant


def _row_to_grant(row: dict) -> LogAccessGrant:
    """把查询结果行转换为 LogAccessGrant 实体。"""
    return LogAccessGrant(
        grant_id=row["grant_id"],
        membership_id=row["membership_id"],
        grant_admin_id=row["grant_admin_id"],
        status=GrantStatus(row["status"]),
        grant_time=row["grant_time"],
        used=bool(row["used"]),
    )


def add(
    membership_id: int,
    grant_admin_id: int,
    status: GrantStatus = GrantStatus.PENDING,
) -> int:
    """新增一条日志查看申请（默认待审批），返回申请 ID。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO log_access_grant "
                "(membership_id, grant_admin_id, status) VALUES (%s, %s, %s)",
                (membership_id, grant_admin_id, status.value),
            )
            return cur.lastrowid


def get_by_id(grant_id: int) -> Optional[LogAccessGrant]:
    """按申请 ID 查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant WHERE grant_id = %s",
                (grant_id,),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def get_valid(membership_id: int) -> Optional[LogAccessGrant]:
    """查询该成员已批准且未使用的有效授权，没有返回 None（一次有效）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant "
                "WHERE membership_id = %s AND status = %s AND used = 0 "
                "ORDER BY grant_id DESC LIMIT 1",
                (membership_id, GrantStatus.APPROVED.value),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def get_pending(membership_id: int) -> Optional[LogAccessGrant]:
    """查询该成员待审批的申请（同一时间至多一份），没有返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant "
                "WHERE membership_id = %s AND status = %s "
                "ORDER BY grant_id DESC LIMIT 1",
                (membership_id, GrantStatus.PENDING.value),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def get_latest(membership_id: int) -> Optional[LogAccessGrant]:
    """查询最近一次申请（用于"一天后重新申请"判断）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM log_access_grant WHERE membership_id = %s "
                "ORDER BY grant_id DESC LIMIT 1",
                (membership_id,),
            )
            row = cur.fetchone()
            return _row_to_grant(row) if row else None


def update_status(grant_id: int, status: GrantStatus) -> None:
    """审批申请：更新状态（已批准 / 已驳回）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE log_access_grant SET status = %s WHERE grant_id = %s",
                (status.value, grant_id),
            )


def mark_used(grant_id: int) -> None:
    """把授权标记为已使用（一次有效，REQ-015）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE log_access_grant SET used = 1 WHERE grant_id = %s",
                (grant_id,),
            )


def list_by_ledger(ledger_id: int) -> list[LogAccessGrant]:
    """查询账本内全部申请/授权记录（超管查看，REQ-015），经成员关系关联。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT g.* FROM log_access_grant g "
                "JOIN membership m ON g.membership_id = m.membership_id "
                "WHERE m.ledger_id = %s ORDER BY g.grant_id DESC",
                (ledger_id,),
            )
            return [_row_to_grant(row) for row in cur.fetchall()]


def list_pending(ledger_id: int, admin_id: int) -> list[LogAccessGrant]:
    """查询指派给某管理员的待审批申请（REQ-015 申请指向具体管理员）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT g.* FROM log_access_grant g "
                "JOIN membership m ON g.membership_id = m.membership_id "
                "WHERE m.ledger_id = %s AND g.grant_admin_id = %s "
                "AND g.status = %s ORDER BY g.grant_id",
                (ledger_id, admin_id, GrantStatus.PENDING.value),
            )
            return [_row_to_grant(row) for row in cur.fetchall()]
