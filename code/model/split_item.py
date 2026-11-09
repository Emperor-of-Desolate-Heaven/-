"""分摊明细实体（类图：分摊明细）。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class SplitItem:
    """分摊明细：一条记录在参与人之间的分摊比例（REQ-013）。

    同一条记录的所有参与人比例之和应为 1。
    """

    split_id: Optional[int] = None
    record_id: int = 0
    user_id: int = 0
    ratio: Decimal = Decimal("0")

    def share_amount(self, total: Decimal) -> Decimal:
        """按比例计算该参与人应分摊的金额，保留两位小数。"""
        return (total * self.ratio).quantize(Decimal("0.01"))
