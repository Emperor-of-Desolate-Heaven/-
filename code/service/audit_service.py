"""审核模块（组件图 SVC_Audit）：审核通过、驳回（REQ-006、REQ-007）。

竞争加锁：状态转换使用条件 UPDATE（见 dao.record_dao.update_status_if /
approve_if_pending），一条记录同一时刻只能由一名管理员成功审核，
其余管理员收到"已被他人处理"的结果——对应时序图"提交与审核"中的
alt 分支"已被其他管理员审核中 → 拒绝审核并提示"。
"""

from dao import log_dao, membership_dao, record_dao
from model.enums import LogOpType, MembershipStatus, RecordStatus
from model.ledger_record import LedgerRecord
from model.operation_log import OperationLog
from service import settle_service


def _require_admin(ledger_id: int, auditor_id: int):
    """审核者须为账本已生效的（超级）管理员（REQ-001、REQ-005）。"""
    member = membership_dao.get(ledger_id, auditor_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    if not member.is_admin:
        raise PermissionError("仅管理员可审核记录")
    return member


def _add_audit_fail_log(ledger_id, auditor_id, submitter_id) -> None:
    """审核失败（驳回）留痕（REQ-015 四类日志之一）。"""
    log_dao.add(OperationLog(
        ledger_id=ledger_id, op_type=LogOpType.AUDIT_FAIL, category="记录审核",
        auditor_id=auditor_id, submitter_id=submitter_id))


def list_pending(
    ledger_id: int, auditor_id: int
) -> list[LedgerRecord]:
    """查看待审核记录列表（REQ-006，仅管理员）。"""
    _require_admin(ledger_id, auditor_id)
    return record_dao.list_by_status(ledger_id, RecordStatus.PENDING)


def approve(record_id: int, auditor_id: int) -> None:
    """审核通过（REQ-006）：待审核 → 已生效。

    转让申请审核通过时，记录上传人同时变为转让目标（REQ-005）。
    竞争加锁：条件更新失败说明已被其他管理员处理。
    """
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    _require_admin(record.ledger_id, auditor_id)
    if record.status is not RecordStatus.PENDING:
        raise ValueError("仅待审核记录可审核")
    result = record_dao.approve_if_pending(record_id)
    if result == 0:
        raise ValueError("该记录正在被其他管理员审核或状态已变化")


def reject(record_id: int, auditor_id: int, reason: str = "") -> None:
    """驳回（REQ-006）：待审核 → 已驳回；也支持驳回已生效记录
    （REQ-007：已生效 → 已驳回，统计自动回退）。

    驳回理由可选（REQ-006 未强制）。
    """
    record = record_dao.get_by_id(record_id)
    if record is None:
        raise ValueError("记录不存在")
    settle_service.ensure_not_settling(record.ledger_id)
    _require_admin(record.ledger_id, auditor_id)
    if not record.can_transition_to(RecordStatus.REJECTED):
        raise ValueError("当前状态不能驳回（仅待审核或已生效记录可驳回）")
    result = record_dao.update_status_if(
        record_id, record.status, RecordStatus.REJECTED, reason
    )
    if result == 0:
        raise ValueError("该记录正在被其他管理员处理或状态已变化")
    _add_audit_fail_log(record.ledger_id, auditor_id, record.submitter_id)
