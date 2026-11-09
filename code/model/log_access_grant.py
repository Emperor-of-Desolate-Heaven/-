"""日志访问授权实体（类图：日志访问授权）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from model.enums import GrantStatus


@dataclass
class LogAccessGrant:
    """日志访问授权：普通成员申请查看日志，管理员审批后一次有效（REQ-015）。

    申请（待审批）→ 管理员审批（已批准/已驳回）→ 成员使用一次后作废；
    上次申请后须隔一天才能重新申请。
    status 列为实现补充设计——类图实体只有"授权"，
    加入申请中间态与 membership.status 同一模式。
    """

    grant_id: Optional[int] = None
    membership_id: int = 0
    grant_admin_id: int = 0
    status: GrantStatus = GrantStatus.PENDING
    grant_time: Optional[datetime] = None
    used: bool = False

    @property
    def is_valid(self) -> bool:
        """授权有效 = 已批准且尚未使用（一次有效，REQ-015）。"""
        return self.status is GrantStatus.APPROVED and not self.used
