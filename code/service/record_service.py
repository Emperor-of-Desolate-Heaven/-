"""收支记录模块（组件图 SVC_Record）：提交、重新提交、修改金额、删除、转让。

权限依据（REQ-005）：
- 普通用户可增加（提交）记录、将记录转让给他人（须经审核）
- 修改金额、删除仅（超级）管理员可执行，且记录须处于已生效状态（REQ-008）
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from dao import ledger_dao, log_dao, membership_dao, record_dao, split_dao, \
    template_dao
from model.enums import Direction, LogOpType, MembershipStatus, RecordStatus
from model.ledger_record import LedgerRecord
from model.operation_log import OperationLog
from model.split_item import SplitItem
from service import settle_service

# 金额上限（REQ-013 未定死具体数值，取 DECIMAL(12,2) 列上限）
MAX_AMOUNT = Decimal("9999999999.99")


def _get_active_member(ledger_id: int, user_id: int):
    """取成员关系，要求是已生效成员。"""
    member = membership_dao.get(ledger_id, user_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return member


def _require_admin(ledger_id: int, operator_id: int):
    """取成员关系并要求（超级）管理员权限（REQ-005 修改/删除）。"""
    member = _get_active_member(ledger_id, operator_id)
    if not member.is_admin:
        raise PermissionError("仅管理员可执行该操作")
    return member


def _parse_amount(raw) -> Decimal:
    """金额校验（REQ-013）：非数字、负数、零、超大数一律拒绝。"""
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ValueError("金额必须是数字") from None
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    if amount > MAX_AMOUNT:
        raise ValueError(f"金额超出允许范围（最大 {MAX_AMOUNT}）")
    return amount.quantize(Decimal("0.01"))


def _check_category(ledger_id: int, category: str) -> None:
    """类别必须来自账本模板的默认类别（REQ-026 模板自带默认类别）。"""
    ledger = ledger_dao.get_by_id(ledger_id)
    template = template_dao.get_by_id(ledger.template_id)
    if category not in template.default_categories:
        raise ValueError(
            f"类别必须是该模板的默认类别之一：{template.default_categories}"
        )


def _check_split_items(ledger_id: int, items: list[SplitItem]) -> None:
    """分摊校验（REQ-013/REQ-026）：参与人须为账本已生效成员，比例之和为 1。"""
    members = {m.user_id for m in membership_dao.list_by_ledger(ledger_id)}
    total = Decimal("0")
    for item in items:
        if item.user_id not in members:
            raise ValueError("分摊参与人必须是账本成员")
        if item.ratio <= 0:
            raise ValueError("分摊比例必须大于 0")
        total += item.ratio
    if items and total != Decimal("1"):
        raise ValueError("分摊比例之和必须为 1")


def _add_log(ledger_id, op_type, category, auditor_id, submitter_id) -> None:
    """操作留痕（REQ-015）。"""
    log_dao.add(OperationLog(
        ledger_id=ledger_id, op_type=op_type, category=category,
        auditor_id=auditor_id, submitter_id=submitter_id))


def submit_record(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    ledger_id: int,
    submitter_id: int,
    category: str,
    reason: str,
    amount,
    direction: Direction,
    record_time: datetime,
    receipt: str = "",
    split_items: Optional[list[SplitItem]] = None,
) -> int:
    """提交收支记录（REQ-004 ~ REQ-007）。

    流程（对应时序图"提交与审核"）：校验成员身份 → 金额校验 →
    类别校验 → 查重 → 落库为待审核 → 保存分摊明细。
    返回新记录 ID。
    """
    settle_service.ensure_not_settling(ledger_id)
    _get_active_member(ledger_id, submitter_id)
    parsed = _parse_amount(amount)
    if not reason.strip():
        raise ValueError("原因不能为空")
    _check_category(ledger_id, category)
    if split_items:
        _check_split_items(ledger_id, split_items)
    # 查重（REQ-014）：除金额外其他三项（原因、时间、凭证）相同即疑似重复
    if record_dao.exists_duplicate(ledger_id, reason, record_time, receipt):
        raise ValueError("疑似重复提交：原因、时间、凭证均相同的记录已存在")
    record = LedgerRecord(
        ledger_id=ledger_id, submitter_id=submitter_id, category=category,
        reason=reason, amount=parsed, direction=direction,
        record_time=record_time, receipt=receipt, status=RecordStatus.PENDING,
    )
    record_id = record_dao.add(record)
    if split_items:
        split_dao.add_batch(record_id, split_items)
    return record_id


def resubmit(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    record_id: int,
    operator_id: int,
    category: str,
    reason: str,
    amount,
    direction: Direction,
    record_time: datetime,
    receipt: str = "",
) -> None:
    """被驳回记录修改后重新提交（REQ-006、REQ-007：已驳回 → 待审核）。

    仅提交人本人可重新提交。
    """
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    if not record.can_transition_to(RecordStatus.PENDING):
        raise ValueError("当前状态不能重新提交（仅已驳回记录可重新提交）")
    if record.submitter_id != operator_id:
        raise PermissionError("仅提交人本人可重新提交")
    parsed = _parse_amount(amount)
    if not reason.strip():
        raise ValueError("原因不能为空")
    _check_category(record.ledger_id, category)
    # 查重排除自己（REQ-014）
    if record_dao.exists_duplicate(
        record.ledger_id, reason, record_time, receipt, exclude_id=record_id
    ):
        raise ValueError("疑似重复提交：原因、时间、凭证均相同的记录已存在")
    record_dao.update_fields(
        record_id, category, reason, parsed, direction, record_time, receipt
    )


def modify_amount(record_id: int, new_amount, operator_id: int) -> None:
    """管理员修改金额（REQ-008）：记录须已生效，状态不变、无需重新审核。"""
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    _require_admin(record.ledger_id, operator_id)
    if record.status is not RecordStatus.ACTIVE:
        raise ValueError("仅已生效记录可修改金额")
    parsed = _parse_amount(new_amount)
    record_dao.update_amount(record_id, parsed)
    _add_log(record.ledger_id, LogOpType.MODIFY, "记录修改",
             operator_id, record.submitter_id)


def delete_record(record_id: int, operator_id: int) -> None:
    """管理员删除记录（REQ-008：取消支出等场景）：已生效 → 已删除，不可恢复。"""
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    _require_admin(record.ledger_id, operator_id)
    if not record.can_transition_to(RecordStatus.DELETED):
        raise ValueError("仅已生效记录可删除")
    result = record_dao.update_status_if(
        record_id, RecordStatus.ACTIVE, RecordStatus.DELETED
    )
    if result == 0:
        raise ValueError("记录状态已变化，删除失败")
    _add_log(record.ledger_id, LogOpType.DELETE, "记录删除",
             operator_id, record.submitter_id)


def apply_transfer(record_id: int, new_owner_id: int, operator_id: int) -> None:
    """发起转让申请（REQ-005）：已生效 → 待审核，转让并入审核流程（REQ-007）。

    仅提交人本人可发起；审核通过后记录归新成员所有。
    """
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    if record.submitter_id != operator_id:
        raise PermissionError("仅提交人本人可发起转让")
    if not record.can_transition_to(RecordStatus.PENDING):
        raise ValueError("当前状态不能转让（仅已生效记录可发起转让）")
    target = membership_dao.get(record.ledger_id, new_owner_id)
    if target is None or target.status is not MembershipStatus.ACTIVE:
        raise ValueError("转让对象必须是该账本的已生效成员")
    result = record_dao.set_transfer(record_id, new_owner_id)
    if result == 0:
        raise ValueError("记录状态已变化，转让失败")


def get_record(record_id: int) -> Optional[LedgerRecord]:
    """查询单条记录。"""
    return record_dao.get_by_id(record_id)


def get_split_items(record_id: int) -> list[SplitItem]:
    """查询记录的分摊明细（REQ-013）。"""
    return split_dao.list_by_record(record_id)
