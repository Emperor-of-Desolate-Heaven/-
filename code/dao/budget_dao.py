"""预算表数据访问（对应类图：预算）。"""

from decimal import Decimal
from typing import Optional

from dao.db import get_connection
from model.budget import Budget


def _row_to_budget(row: dict) -> Budget:
    """把查询结果行转换为 Budget 实体。"""
    return Budget(
        budget_id=row["budget_id"],
        ledger_id=row["ledger_id"],
        amount=row["amount"],
        enabled=bool(row["enabled"]),
    )


def upsert(ledger_id: int, amount: Decimal, enabled: bool = True) -> None:
    """设置或更新账本预算（一个账本至多一份预算，REQ-019）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO budget (ledger_id, amount, enabled) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE amount = %s, enabled = %s",
                (ledger_id, amount, 1 if enabled else 0, amount,
                 1 if enabled else 0),
            )


def get_by_ledger(ledger_id: int) -> Optional[Budget]:
    """查询账本预算，未设置返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM budget WHERE ledger_id = %s", (ledger_id,)
            )
            row = cur.fetchone()
            return _row_to_budget(row) if row else None
