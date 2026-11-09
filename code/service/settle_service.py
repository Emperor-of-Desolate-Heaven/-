"""结算模块（组件图 SVC_Settle）：按模板自动结算（REQ-011）、结算锁（REQ-012）。

结算规则（REQ-011 / REQ-026）：
- 旅行：结束时一次性结算（AA 均摊，输出总收支与记录条数）
- 合租：每月固定日期结算，输出每人应付明细（按分摊比例）
- 家庭：不结算
结算时间点为结算当日 0:00（REQ-011）；只统计 0:00 前已生效的记录，
待审核等状态不参与结算（REQ-012）。结算期间置结算锁，其他操作一律
拒绝并提示"请等到结算后再操作"（REQ-012）。

实现补充口径：
- 结算由（超级）管理员触发（需求未明确触发者，人工定）；
- 无分摊明细的记录在"每人应付明细"中全额归属提交人。
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from dao import (ledger_dao, membership_dao, record_dao, settlement_dao,
                 split_dao, template_dao, user_dao)
from model.enums import Direction, MembershipStatus
from model.settlement import Settlement

SETTLING_MESSAGE = "请等到结算后再操作"


@dataclass
class SettlementSummary:
    """一次结算的计算结果（未落库）。"""

    total_expense: Decimal = Decimal("0")
    total_income: Decimal = Decimal("0")
    record_count: int = 0
    per_person: dict = field(default_factory=dict)  # user_id -> 应付金额


def ensure_not_settling(ledger_id: int) -> None:
    """结算期间拒绝一切操作（REQ-012）。各业务模块入口先调用本函数。"""
    if ledger_dao.is_settling(ledger_id):
        raise ValueError(SETTLING_MESSAGE)


def _require_admin(ledger_id: int, operator_id: int):
    """取成员关系并要求（超级）管理员权限（结算触发权限，人工定）。"""
    member = membership_dao.get(ledger_id, operator_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    if not member.is_admin:
        raise PermissionError("仅管理员可执行结算")
    return member


def _cutoff(settle_at: datetime) -> datetime:
    """结算时间点 = 结算当日 0:00（REQ-011）。"""
    return settle_at.replace(hour=0, minute=0, second=0, microsecond=0)


def _period_start(ledger_id: int) -> datetime:
    """结算周期起点：上一次结算时间点；首次结算为账本生效时间。"""
    latest = settlement_dao.get_latest(ledger_id)
    if latest is not None and latest.settle_time is not None:
        return latest.settle_time
    return ledger_dao.get_by_id(ledger_id).effective_time


def _compute(
    ledger_id: int,
    template_type: str,
    period_start: datetime,
    settle_time: datetime,
) -> SettlementSummary:
    """统计周期内已生效记录，并计算合租账本的每人应付明细。"""
    records = record_dao.list_active_between(
        ledger_id, period_start, settle_time
    )
    summary = SettlementSummary(record_count=len(records))
    for record in records:
        if record.direction is Direction.EXPENSE:
            summary.total_expense += record.amount
        else:
            summary.total_income += record.amount
    if template_type == "合租":
        for record in records:
            if record.direction is not Direction.EXPENSE:
                continue  # 应付明细只分摊支出；收入仅计入总收入
            items = split_dao.list_by_record(record.record_id)
            if items:
                for item in items:
                    share = item.share_amount(record.amount)
                    summary.per_person[item.user_id] = (
                        summary.per_person.get(item.user_id, Decimal("0"))
                        + share
                    )
            else:
                # 无分摊明细的记录全额归属提交人（实现补充口径）
                summary.per_person[record.submitter_id] = (
                    summary.per_person.get(
                        record.submitter_id, Decimal("0")
                    )
                    + record.amount
                )
    return summary


def _format_result(template_type: str, summary: SettlementSummary) -> str:
    """结算结果摘要（REQ-011：总收支、记录条数；合租另附每人应付明细）。"""
    parts = [
        f"总支出 {summary.total_expense:.2f} 元",
        f"总收入 {summary.total_income:.2f} 元",
        f"记录 {summary.record_count} 条",
    ]
    if template_type == "合租" and summary.per_person:
        names = []
        for user_id, payable in sorted(summary.per_person.items()):
            user = user_dao.get_by_id(user_id)
            label = user.username if user else f"用户{user_id}"
            names.append(f"{label} {payable:.2f} 元")
        parts.append("每人应付：" + "，".join(names))
    return "，".join(parts)


def settle(
    ledger_id: int,
    operator_id: int,
    settle_at: Optional[datetime] = None,
) -> Settlement:
    """执行一次结算（REQ-011 / REQ-012）。

    settle_at 缺省为当前时间；结算时间点取当日 0:00。
    结算期间置结算锁（其他操作被拒绝），结算完成后释放。
    返回落库的结算结果。
    """
    _require_admin(ledger_id, operator_id)
    ledger = ledger_dao.get_by_id(ledger_id)
    template = template_dao.get_by_id(ledger.template_id)
    if not template.supports_settlement:
        raise ValueError("家庭账本不结算（REQ-026）")
    settle_time = _cutoff(settle_at or datetime.now())
    period_start = _period_start(ledger_id)
    try:
        ledger_dao.set_settling(ledger_id, True)
        summary = _compute(
            ledger_id, template.template_type, period_start, settle_time
        )
        settlement = Settlement(
            ledger_id=ledger_id,
            settle_time=settle_time,
            period=f"{period_start:%Y-%m-%d %H:%M} 至 "
                   f"{settle_time:%Y-%m-%d %H:%M}",
            result=_format_result(template.template_type, summary),
        )
        settlement.settle_id = settlement_dao.add(settlement)
        return settlement
    finally:
        ledger_dao.set_settling(ledger_id, False)


def list_settlements(ledger_id: int, viewer_id: int) -> list[Settlement]:
    """查询账本历史结算记录（REQ-011，只读展示）。"""
    member = membership_dao.get(ledger_id, viewer_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return settlement_dao.list_by_ledger(ledger_id)
