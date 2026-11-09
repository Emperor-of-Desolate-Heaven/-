"""结算实体（类图：结算）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Settlement:
    """结算结果：系统按账本模板自动结算后生成（REQ-011、REQ-026）。

    结算由后台自动执行，界面只做只读展示。
    """

    settle_id: Optional[int] = None
    ledger_id: int = 0
    settle_time: Optional[datetime] = None
    period: str = ""
    result: str = ""
