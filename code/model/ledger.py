"""账本实体（类图：账本）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Ledger:
    """账本：多人共享记账的基本单位。

    创建时必须选择一个场景模板（REQ-002、REQ-026），
    生效时间为账本创建时间。
    """

    ledger_id: Optional[int] = None
    name: str = ""
    template_id: int = 0
    effective_time: Optional[datetime] = None
