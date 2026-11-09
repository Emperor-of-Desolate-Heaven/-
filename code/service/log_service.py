"""日志模块（组件图 SVC_Log）：操作日志查看与访问授权（REQ-015）。

- 加入/删除/修改/审核失败四类操作日志：管理员可直接查看；
  普通成员须向管理员申请，审批通过后获得一次访问权限（一次有效），
  使用后须隔一天才能重新申请。
- 管理员每次查看日志写入一条"查看日志"记录；
  超管可查看这些记录，以及全部申请/授权/使用记录（REQ-015）。
"""

from datetime import datetime, timedelta

from dao import grant_dao, log_dao, membership_dao
from model.enums import GrantStatus, LogOpType, MembershipStatus
from model.log_access_grant import LogAccessGrant
from model.operation_log import OperationLog
from service import settle_service

# 重新申请冷却期（REQ-015：下次访问须在一天后重新申请）
APPLY_COOLDOWN = timedelta(days=1)


def _require_member(ledger_id: int, user_id: int):
    """取成员关系，要求是已生效成员。"""
    member = membership_dao.get(ledger_id, user_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return member


def _require_super_admin(ledger_id: int, user_id: int):
    """取成员关系并要求超管权限（REQ-015：超管可查看授权与查看记录）。"""
    member = _require_member(ledger_id, user_id)
    if not member.is_super_admin:
        raise PermissionError("仅超级管理员可查看该记录")
    return member


def view_logs(ledger_id: int, viewer_id: int) -> list[OperationLog]:
    """查看账本操作日志（REQ-015）。

    管理员（含超管）直接可看，且查看动作留痕为"查看日志"类型记录；
    普通成员须持有有效授权，本次查看后授权作废（一次有效）。
    """
    member = _require_member(ledger_id, viewer_id)
    if member.is_admin:
        log_dao.add(OperationLog(
            ledger_id=ledger_id,
            op_type=LogOpType.VIEW,
            category="日志查看",
            auditor_id=viewer_id,
        ))
        return log_dao.list_by_ledger(ledger_id)
    grant = grant_dao.get_valid(member.membership_id)
    if grant is None:
        raise PermissionError("无有效授权：请先向管理员申请日志查看")
    grant_dao.mark_used(grant.grant_id)
    return log_dao.list_by_ledger(ledger_id)


def request_view(ledger_id: int, member_id: int, admin_id: int) -> int:
    """普通成员向某管理员发起日志查看申请（REQ-015），返回申请 ID。

    限制：已有有效授权或待审批申请时不能重复申请；
    距上次申请（无论结果）不足一天时不能再次申请。
    """
    settle_service.ensure_not_settling(ledger_id)
    member = _require_member(ledger_id, member_id)
    admin = _require_member(ledger_id, admin_id)
    if not admin.is_admin:
        raise ValueError("申请对象必须是账本管理员")
    if grant_dao.get_valid(member.membership_id) is not None:
        raise ValueError("已有有效授权，请直接查看日志")
    if grant_dao.get_pending(member.membership_id) is not None:
        raise ValueError("已有待审批的日志查看申请")
    latest = grant_dao.get_latest(member.membership_id)
    if latest is not None and latest.grant_time is not None:
        if datetime.now() - latest.grant_time < APPLY_COOLDOWN:
            raise ValueError("距上次申请不足一天，请一天后再申请")
    return grant_dao.add(member.membership_id, admin_id)


def list_applications(
    ledger_id: int, admin_id: int
) -> list[LogAccessGrant]:
    """管理员查看指派给自己的待审批日志查看申请（REQ-015）。"""
    admin = _require_member(ledger_id, admin_id)
    if not admin.is_admin:
        raise PermissionError("仅管理员可查看日志访问申请")
    return grant_dao.list_pending(ledger_id, admin_id)


def _require_target_admin(grant_id: int, admin_id: int):
    """取待审批申请并要求操作者是指派的管理员本人（REQ-015）。"""
    grant = grant_dao.get_by_id(grant_id)
    if grant is None or grant.status is not GrantStatus.PENDING:
        raise ValueError("申请不存在或已处理")
    membership = membership_dao.get_by_id(grant.membership_id)
    settle_service.ensure_not_settling(membership.ledger_id)
    admin = _require_member(membership.ledger_id, admin_id)
    if not admin.is_admin:
        raise PermissionError("仅管理员可审批日志查看申请")
    if grant.grant_admin_id != admin_id:
        raise PermissionError("只能审批指派给自己的申请")
    return grant


def approve_request(grant_id: int, admin_id: int) -> None:
    """管理员审批通过日志查看申请（REQ-015）：待审批 → 已批准，可用一次。"""
    _require_target_admin(grant_id, admin_id)
    grant_dao.update_status(grant_id, GrantStatus.APPROVED)


def reject_request(grant_id: int, admin_id: int) -> None:
    """管理员驳回日志查看申请（REQ-015）：待审批 → 已驳回。"""
    _require_target_admin(grant_id, admin_id)
    grant_dao.update_status(grant_id, GrantStatus.REJECTED)


def list_grants(
    ledger_id: int, super_admin_id: int
) -> list[LogAccessGrant]:
    """超管查看账本内全部申请/授权/使用记录（REQ-015）。

    grant_time 为申请时间；used=1 表示成员已使用授权查看过日志。
    """
    _require_super_admin(ledger_id, super_admin_id)
    return grant_dao.list_by_ledger(ledger_id)


def list_view_records(
    ledger_id: int, super_admin_id: int
) -> list[OperationLog]:
    """超管查看"管理员查看日志"的记录（REQ-015）。"""
    _require_super_admin(ledger_id, super_admin_id)
    return log_dao.list_by_type(ledger_id, LogOpType.VIEW)
