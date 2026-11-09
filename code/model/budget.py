"""预算实体（类图：预算）。"""

from dataclasses import dataclass
from decimal import Decimal

# 红绿灯阈值（REQ-019）：低于 80% 绿，80% ~ 100% 黄，超过 100% 红
GREEN_THRESHOLD = Decimal("0.8")
RED_THRESHOLD = Decimal("1.0")


@dataclass
class Budget:
    """账本预算：可选设置，由超级管理员配置（REQ-019）。

    未设置预算时报警器不启用，主页显示"未设置预算"。
    """

    budget_id: int = 0
    ledger_id: int = 0
    amount: Decimal = Decimal("0.00")
    enabled: bool = True

    def usage_ratio(self, total_expense: Decimal) -> Decimal:
        """计算支出占预算的比例；预算金额非正时视为已超标。"""
        if self.amount <= 0:
            return Decimal("Infinity")
        return total_expense / self.amount

    def traffic_light(self, total_expense: Decimal) -> str:
        """返回红绿灯等级：绿 / 黄 / 红（REQ-019）。"""
        ratio = self.usage_ratio(total_expense)
        if ratio < GREEN_THRESHOLD:
            return "绿"
        if ratio <= RED_THRESHOLD:
            return "黄"
        return "红"
