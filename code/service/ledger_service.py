"""账本与模板模块（组件图 SVC_Ledger）：账本创建与查询（REQ-002、REQ-026）。"""

from dao import ledger_dao, membership_dao, template_dao
from model.enums import MembershipStatus, Role
from model.ledger import Ledger


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
