"""日志访问授权实体（类图：日志访问授权）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LogAccessGrant:
    """日志访问授权：普通成员申请查看日志，管理员审批后一次有效（REQ-015）。

    授权使用后须一天后才能重新申请。
    """

    grant_id: Optional[int] = None
    membership_id: int = 0
    grant_admin_id: int = 0
    grant_time: Optional[datetime] = None
    used: bool = False

    @property
    def is_valid(self) -> bool:
        """授权尚未使用才有效（一次有效，REQ-015）。"""
        return not self.used
