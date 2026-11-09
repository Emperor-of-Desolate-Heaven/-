"""预算报警模块（组件图 SVC_Budget）：设置预算（仅超管）、红绿灯（REQ-019）。

红绿灯：总支出低于预算 80% 绿、80%~100% 黄、超过 100% 红；
未设置预算的账本不启用报警器（主页显示"未设置预算"）。
"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from dao import budget_dao, membership_dao, record_dao
from model.budget import Budget
from model.enums import Direction, MembershipStatus
from service import settle_service


def _require_super_admin(ledger_id: int, operator_id: int):
    """取成员关系并要求超管权限（REQ-019：预算由超级管理员设置）。"""
    member = membership_dao.get(ledger_id, operator_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    if not member.is_super_admin:
        raise PermissionError("仅超级管理员可设置预算")
    return member


def set_budget(
    ledger_id: int,
    operator_id: int,
    amount,
    enabled: bool = True,
) -> None:
    """超管设置账本预算（REQ-019）；一个账本至多一份预算，重复设置即更新。"""
    settle_service.ensure_not_settling(ledger_id)
    _require_super_admin(ledger_id, operator_id)
    try:
        parsed = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError("预算金额必须是数字") from None
    if parsed <= 0:
        raise ValueError("预算金额必须大于 0")
    budget_dao.upsert(ledger_id, parsed.quantize(Decimal("0.01")), enabled)


def get_budget(ledger_id: int, viewer_id: int) -> Optional[Budget]:
    """查询账本预算（REQ-019 报警器所有成员可见）；未设置返回 None。"""
    member = membership_dao.get(ledger_id, viewer_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return budget_dao.get_by_ledger(ledger_id)


def get_traffic_light(ledger_id: int, viewer_id: int) -> Optional[str]:
    """预算红绿灯（REQ-019）：所有成员可见；未设置或停用返回 None。

    返回 "绿" / "黄" / "红"。
    """
    member = membership_dao.get(ledger_id, viewer_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    budget = budget_dao.get_by_ledger(ledger_id)
    if budget is None or not budget.enabled:
        return None
    total_expense = record_dao.sum_by_direction(
        ledger_id, Direction.EXPENSE
    )
    return budget.traffic_light(total_expense)
