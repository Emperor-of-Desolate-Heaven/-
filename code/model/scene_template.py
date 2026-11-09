"""场景模板实体（类图：场景模板）。"""

from dataclasses import dataclass, field


@dataclass
class SceneTemplate:
    """账本场景模板：决定账本的默认类别、结算方式与预算口径（REQ-026）。

    系统预置旅行 / 合租 / 家庭三套模板，账本创建时必须且只能选择一个（REQ-002）。
    """

    template_id: int = 0
    template_type: str = ""
    default_categories: list[str] = field(default_factory=list)
    settle_method: str = ""  # 旅行：AA均摊；合租：按分摊比例；家庭：不结算
    budget_caliber: str = ""  # 预算口径：总支出

    @property
    def supports_settlement(self) -> bool:
        """家庭模板不提供结算（REQ-026）。"""
        return self.settle_method != "不结算"
