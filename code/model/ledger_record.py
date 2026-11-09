"""收支记录实体（类图：收支记录）。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from model.enums import Direction, RecordStatus

# 状态机允许的转换（REQ-007）：键为当前状态，值为可转换到的目标状态集合。
# 已生效 → 待审核 仅用于转让申请并入审核流程。
ALLOWED_TRANSITIONS = {
    RecordStatus.PENDING: {RecordStatus.ACTIVE, RecordStatus.REJECTED},
    RecordStatus.REJECTED: {RecordStatus.PENDING},
    RecordStatus.ACTIVE: {
        RecordStatus.REJECTED,
        RecordStatus.PENDING,
        RecordStatus.DELETED,
    },
    RecordStatus.DELETED: set(),
}

# 禁止的转换（REQ-007）：
# - 已驳回 → 已生效：必须重新提交并经过审核
# - 已生效 → 待审核：仅转让申请允许；手工退回须先驳回再重新提交
# - 已删除 → 任何状态：不可恢复


@dataclass
class LedgerRecord:
    """收支记录：账本中的一笔收入或支出（REQ-004 ~ REQ-008）。"""

    record_id: Optional[int] = None
    ledger_id: int = 0
    submitter_id: int = 0
    transfer_to: Optional[int] = None  # 转让申请目标（审核通过后成为新上传人）
    category: str = ""
    reason: str = ""
    amount: Decimal = Decimal("0.00")
    direction: Direction = Direction.EXPENSE  # 金额恒为正，收支由方向区分
    record_time: Optional[datetime] = None
    receipt: str = ""  # 支付凭证（可选）
    status: RecordStatus = RecordStatus.PENDING
    reject_reason: str = ""

    @property
    def is_locked(self) -> bool:
        """待审核期间记录被锁定，不支持再次转让、修改金额、删除等操作（REQ-007）。"""
        return self.status is RecordStatus.PENDING

    def can_transition_to(self, target: RecordStatus) -> bool:
        """判断当前状态能否转换到目标状态。"""
        return target in ALLOWED_TRANSITIONS[self.status]
