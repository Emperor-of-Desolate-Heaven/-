"""成员关系实体（类图：成员关系）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from model.enums import MembershipStatus, Role


@dataclass
class Membership:
    """成员关系：用户加入账本后产生，承载该用户在账本内的角色与可见性设置。

    角色和可见性是"用户在某个账本中的属性"，同一用户在不同账本中
    角色可以不同（REQ-001、REQ-022）。
    """

    membership_id: Optional[int] = None
    ledger_id: int = 0
    user_id: int = 0
    role: Role = Role.MEMBER
    status: MembershipStatus = MembershipStatus.ACTIVE
    join_time: Optional[datetime] = None
    # 合租场景：提交人的记录对其他成员是否可见（REQ-022）
    visibility_on: bool = True

    @property
    def is_admin(self) -> bool:
        """管理员及以上（管理员 / 超级管理员 / 创建者）。"""
        return self.role.level >= Role.ADMIN.level

    @property
    def is_super_admin(self) -> bool:
        """超级管理员或创建者。"""
        return self.role.level >= Role.SUPER_ADMIN.level
