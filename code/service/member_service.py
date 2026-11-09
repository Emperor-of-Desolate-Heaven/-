"""成员管理模块（组件图 SVC_Member）：加入申请、拉人、角色、超管转让、可见性、退出。

权限依据（REQ-001 / REQ-003 / REQ-022，人工确认后）：
- 仅超级管理员可以拉人、审批加入申请、踢人、修改他人角色（REQ-001；
  REQ-003 旧文"管理员可拉入"与 REQ-001 矛盾，按 REQ-001 实现）
- 超管身份转让后原超管降为普通用户（INT-03-L01/L02 未明确降到哪级，
  人工拍板为普通用户）
- 合租账本的记录可见性由提交人本人整体设置（REQ-022），其他模板无此开关
"""

from dao import (ledger_dao, log_dao, membership_dao, record_dao,
                 template_dao, user_dao)
from model.enums import LogOpType, MembershipStatus, RecordStatus, Role
from model.membership import Membership
from model.operation_log import OperationLog
from service import settle_service

# 退出成员待审核记录的驳回理由（REQ-003 异常边界：直接审核失败）
EXIT_REJECT_REASON = "成员退出，待审核记录审核失败"


def _get_operator(ledger_id: int, operator_id: int) -> Membership:
    """取操作者的成员关系；不是已生效成员则拒绝。"""
    operator = membership_dao.get(ledger_id, operator_id)
    if operator is None or operator.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    return operator


def _require_super_admin(ledger_id: int, operator_id: int) -> Membership:
    """取操作者成员关系并要求具备超管权限。"""
    operator = _get_operator(ledger_id, operator_id)
    if not operator.is_super_admin:
        raise PermissionError("仅超级管理员可执行该操作")
    return operator


def _add_log(
    ledger_id: int,
    op_type: LogOpType,
    category: str,
    auditor_id: int,
    submitter_id: int,
) -> None:
    """操作留痕（REQ-015）。"""
    log_dao.add(
        OperationLog(
            ledger_id=ledger_id,
            op_type=op_type,
            category=category,
            auditor_id=auditor_id,
            submitter_id=submitter_id,
        )
    )


# ---------- 加入 ----------

def apply_join(ledger_id: int, user_id: int) -> int:
    """成员向超管发送加入申请（REQ-003）：生成一条待审核成员关系。"""
    settle_service.ensure_not_settling(ledger_id)
    if ledger_dao.get_by_id(ledger_id) is None:
        raise ValueError("账本不存在")
    if membership_dao.get(ledger_id, user_id) is not None:
        raise ValueError("你已申请或已加入该账本")
    return membership_dao.add(ledger_id, user_id, Role.MEMBER,
                              MembershipStatus.PENDING)


def list_applications(ledger_id: int, operator_id: int) -> list[Membership]:
    """查看待审核加入申请（仅超管）。"""
    _require_super_admin(ledger_id, operator_id)
    return membership_dao.list_pending(ledger_id)


def approve_join(membership_id: int, operator_id: int) -> None:
    """审批通过加入申请（仅超管），并记录"加入"日志。"""
    target = membership_dao.get_by_id(membership_id)
    if target is None or target.status is not MembershipStatus.PENDING:
        raise ValueError("申请不存在或已处理")
    settle_service.ensure_not_settling(target.ledger_id)
    _require_super_admin(target.ledger_id, operator_id)
    membership_dao.update_status(membership_id, MembershipStatus.ACTIVE)
    _add_log(target.ledger_id, LogOpType.JOIN, "成员",
             operator_id, target.user_id)


def reject_join(membership_id: int, operator_id: int) -> None:
    """拒绝加入申请（仅超管）：删除待审核行。"""
    target = membership_dao.get_by_id(membership_id)
    if target is None or target.status is not MembershipStatus.PENDING:
        raise ValueError("申请不存在或已处理")
    settle_service.ensure_not_settling(target.ledger_id)
    _require_super_admin(target.ledger_id, operator_id)
    membership_dao.remove(membership_id)


def pull_in(ledger_id: int, username: str, operator_id: int) -> None:
    """超管按用户名直接拉人入账本（REQ-003），并记录"加入"日志。"""
    settle_service.ensure_not_settling(ledger_id)
    _require_super_admin(ledger_id, operator_id)
    user = user_dao.get_by_username(username.strip())
    if user is None:
        raise ValueError("用户不存在")
    if membership_dao.get(ledger_id, user.user_id) is not None:
        raise ValueError("该用户已申请或已加入该账本")
    membership_dao.add(ledger_id, user.user_id, Role.MEMBER,
                       MembershipStatus.ACTIVE)
    _add_log(ledger_id, LogOpType.JOIN, "成员",
             operator_id, user.user_id)


# ---------- 角色 ----------

def set_role(membership_id: int, new_role: Role, operator_id: int) -> None:
    """超管修改成员角色（REQ-001）。

    限制（保证"一个账本只能有一个超管"）：
    - 不能把成员设为超管/创建者（超管产生只能走转让流程）
    - 不能修改当前超管权限者的角色（超管变更只能走转让流程）
    """
    target = membership_dao.get_by_id(membership_id)
    if target is None or target.status is not MembershipStatus.ACTIVE:
        raise ValueError("成员不存在")
    settle_service.ensure_not_settling(target.ledger_id)
    _require_super_admin(target.ledger_id, operator_id)
    if target.is_super_admin:
        raise PermissionError("超管角色只能通过身份转让变更")
    if new_role in (Role.SUPER_ADMIN, Role.CREATOR):
        raise PermissionError("不能直接设置超管角色，请使用身份转让")
    membership_dao.update_role(membership_id, new_role)
    _add_log(target.ledger_id, LogOpType.MODIFY, "角色",
             operator_id, target.user_id)


def transfer_super_admin(
    ledger_id: int, new_admin_id: int, operator_id: int
) -> None:
    """超管身份转让（REQ-001）：新超管须为已生效成员；原超管降为普通用户。"""
    settle_service.ensure_not_settling(ledger_id)
    _require_super_admin(ledger_id, operator_id)
    target = membership_dao.get(ledger_id, new_admin_id)
    if target is None or target.status is not MembershipStatus.ACTIVE:
        raise ValueError("转让对象不是该账本的有效成员")
    if target.is_super_admin:
        raise ValueError("该成员已是超级管理员")
    # 一个账本只能有一个超管：先把现有超管权限者全部降为普通用户
    for member in membership_dao.list_by_ledger(ledger_id):
        if member.is_super_admin:
            membership_dao.update_role(member.membership_id, Role.MEMBER)
    membership_dao.update_role(target.membership_id, Role.SUPER_ADMIN)
    _add_log(ledger_id, LogOpType.MODIFY, "超管转让",
             operator_id, new_admin_id)


# ---------- 可见性 ----------

def set_visibility(
    membership_id: int, visibility_on: bool, operator_id: int
) -> None:
    """记录可见性整体设置（REQ-022）。

    仅合租账本提供该开关；由提交人本人设置（对其全部记录生效）。
    """
    target = membership_dao.get_by_id(membership_id)
    if target is None or target.status is not MembershipStatus.ACTIVE:
        raise ValueError("成员不存在")
    settle_service.ensure_not_settling(target.ledger_id)
    if target.user_id != operator_id:
        raise PermissionError("可见性只能由本人设置")
    ledger = ledger_dao.get_by_id(target.ledger_id)
    template = template_dao.get_by_id(ledger.template_id)
    if template.template_type != "合租":
        raise PermissionError("该模板不支持可见性设置（仅合租账本）")
    membership_dao.set_visibility(membership_id, visibility_on)


# ---------- 退出 / 踢人 ----------

def remove_member(
    membership_id: int,
    operator_id: int,
    transfer_to: int | None = None,
    cancel_records: bool = False,
) -> None:
    """成员退出或超管踢人（REQ-003）。

    记录处理：待审核记录直接审核失败；其余记录按选择转让
    （默认转让给账本管理员，无管理员则超管）或注销。
    超管退出须先转让身份。
    """
    target = membership_dao.get_by_id(membership_id)
    if target is None or target.status is not MembershipStatus.ACTIVE:
        raise ValueError("成员不存在")
    ledger_id = target.ledger_id
    settle_service.ensure_not_settling(ledger_id)
    operator = _get_operator(ledger_id, operator_id)
    if not (operator.is_super_admin or operator.user_id == target.user_id):
        raise PermissionError("仅超管可移除成员，成员本人可退出")
    if target.is_super_admin:
        raise PermissionError("超管请先转让身份再退出")

    # 1. 待审核记录直接审核失败（REQ-003 异常边界）
    pending_cnt = record_dao.reject_all_pending_by_submitter(
        ledger_id, target.user_id, EXIT_REJECT_REASON
    )
    if pending_cnt > 0:
        _add_log(ledger_id, LogOpType.AUDIT_FAIL, "成员退出",
                 operator_id, target.user_id)

    # 2. 其余记录：转让或注销
    if cancel_records:
        record_dao.delete_all_by_submitter(ledger_id, target.user_id)
    else:
        new_owner_id = transfer_to or _default_transfer_target(
            ledger_id, target.user_id
        )
        record_dao.update_submitter_by_owner(
            ledger_id, target.user_id, new_owner_id
        )

    # 3. 移除成员并留痕
    membership_dao.remove(membership_id)
    _add_log(ledger_id, LogOpType.DELETE, "成员",
             operator_id, target.user_id)


def _default_transfer_target(ledger_id: int, leaving_user_id: int) -> int:
    """退出时记录的默认转让对象：账本内第一个管理员；没有管理员则超管。"""
    members = membership_dao.list_by_ledger(ledger_id)
    others = [m for m in members if m.user_id != leaving_user_id]
    for member in others:
        if member.role is Role.ADMIN:
            return member.user_id
    for member in others:
        if member.is_super_admin:
            return member.user_id
    raise ValueError("账本没有可转让的成员，请选择注销记录")
