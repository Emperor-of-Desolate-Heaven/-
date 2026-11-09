"""操作日志实体（类图：操作日志）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from model.enums import LogOpType


@dataclass
class OperationLog:
    """操作日志：记录加入、删除、修改、审核失败四类操作（REQ-015）。

    日志内容包含审核人、提交人、日期、类别。
    """

    log_id: Optional[int] = None
    ledger_id: int = 0
    op_type: LogOpType = LogOpType.JOIN
    category: str = ""
    auditor_id: Optional[int] = None
    submitter_id: Optional[int] = None
    log_time: Optional[datetime] = None
