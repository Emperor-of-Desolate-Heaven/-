"""查询统计模块（组件图 SVC_Stats）：主页统计（REQ-010）、组合查询（REQ-009）。

统计口径只含已生效记录（REQ-017：审核通过后统计立即更新，
驳回/删除后统计回退）。
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from dao import ledger_dao, membership_dao, record_dao, template_dao
from model.enums import Direction, MembershipStatus
from model.ledger_record import LedgerRecord


@dataclass
class LedgerSummary:
    """账本主页统计信息（REQ-010）：所有成员可见，不做读写权限分离。"""

    total_expense: Decimal = Decimal("0")
    total_income: Decimal = Decimal("0")
    net: Decimal = Decimal("0")  # 净收支差 = 总收入 - 总支出
    effective_time: Optional[datetime] = None


def _require_member(ledger_id: int, user_id: int):
    """取成员关系，要求是已生效成员。"""
    member = membership_dao.get(ledger_id, user_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return member


def get_summary(ledger_id: int, viewer_id: int) -> LedgerSummary:
    """账本主页统计（REQ-010）：总支出、总收入、净收支差、账本生效时间。"""
    _require_member(ledger_id, viewer_id)
    ledger = ledger_dao.get_by_id(ledger_id)
    expense = record_dao.sum_by_direction(ledger_id, Direction.EXPENSE)
    income = record_dao.sum_by_direction(ledger_id, Direction.INCOME)
    return LedgerSummary(
        total_expense=expense,
        total_income=income,
        net=income - expense,
        effective_time=ledger.effective_time,
    )


def query_records(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ledger_id: int,
    viewer_id: int,
    category: Optional[str] = None,
    submitter_id: Optional[int] = None,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
    amount_min: Optional[Decimal] = None,
    amount_max: Optional[Decimal] = None,
) -> list[LedgerRecord]:
    """按类别/成员/时间/金额组合查询（REQ-009），并应用可见性规则（REQ-022）。

    可见性：合租账本普通成员只看到自己提交的记录和开启可见性成员提交的
    记录；旅行/家庭账本成员间全部可见。管理员承担修改/删除职责
    （REQ-008），可查看全部记录。
    """
    member = _require_member(ledger_id, viewer_id)
    records = record_dao.query(
        ledger_id, category, submitter_id,
        time_from, time_to, amount_min, amount_max,
    )
    ledger = ledger_dao.get_by_id(ledger_id)
    template = template_dao.get_by_id(ledger.template_id)
    if template.template_type == "合租" and not member.is_admin:
        visible = {
            m.user_id
            for m in membership_dao.list_by_ledger(ledger_id)
            if m.visibility_on
        }
        visible.add(viewer_id)  # 自己的记录始终可见
        records = [r for r in records if r.submitter_id in visible]
    return records
