"""账本与模板模块（组件图 SVC_Ledger）：账本创建与查询（REQ-002、REQ-026）。"""

from dao import ledger_dao, membership_dao, template_dao
from model.enums import MembershipStatus, Role
from model.ledger import Ledger
from model.membership import Membership
from model.scene_template import SceneTemplate


def create_ledger(name: str, template_id: int, creator_id: int) -> int:
    """创建账本：必须选择存在的场景模板；创建者自动成为账本第一个成员。

    创建者角色为"创建者"，默认即超级管理员（REQ-001）。
    返回新账本 ID。
    """
    name = name.strip()
    if not name:
        raise ValueError("账本名称不能为空")
    if template_dao.get_by_id(template_id) is None:
        raise ValueError("场景模板不存在")
    ledger_id = ledger_dao.add(name, template_id)
    membership_dao.add(ledger_id, creator_id, Role.CREATOR,
                       MembershipStatus.ACTIVE)
    return ledger_id


def list_ledgers_by_user(user_id: int) -> list[Ledger]:
    """查询用户加入的全部账本（REQ-010 主页账本切换）。"""
    return ledger_dao.list_by_user(user_id)


def list_ledgers_with_membership(
    user_id: int,
) -> list[tuple[Ledger, Membership]]:
    """查询用户参与的全部账本及成员关系（含待审核申请，界面展示用）。"""
    return ledger_dao.list_with_membership_by_user(user_id)


def list_templates() -> list[SceneTemplate]:
    """查询系统预置的三套场景模板（创建账本时选择，REQ-026）。"""
    return template_dao.list_all()


def get_ledger_detail(
    ledger_id: int, user_id: int
) -> tuple[Ledger, SceneTemplate]:
    """查询账本详情（账本 + 所用模板），要求查看者是账本已生效成员。"""
    member = membership_dao.get(ledger_id, user_id)
    if member is None or member.status is not MembershipStatus.ACTIVE:
        raise PermissionError("你不是该账本的成员")
    ledger = ledger_dao.get_by_id(ledger_id)
    template = template_dao.get_by_id(ledger.template_id)
    return ledger, template
