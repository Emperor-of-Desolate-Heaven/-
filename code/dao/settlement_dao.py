"""结算表数据访问（对应类图：结算）。"""

from typing import Optional

from dao.db import get_connection
from model.settlement import Settlement


def _row_to_settlement(row: dict) -> Settlement:
    """把查询结果行转换为 Settlement 实体。"""
    return Settlement(
        settle_id=row["settle_id"],
        ledger_id=row["ledger_id"],
        settle_time=row["settle_time"],
        period=row["period"],
        result=row["result"] or "",
    )


def add(settlement: Settlement) -> int:
    """保存一次结算结果（REQ-011）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO settlement (ledger_id, settle_time, period, result) "
                "VALUES (%s, %s, %s, %s)",
                (
                    settlement.ledger_id,
                    settlement.settle_time,
                    settlement.period,
                    settlement.result,
                ),
            )
            return cur.lastrowid


def list_by_ledger(ledger_id: int) -> list[Settlement]:
    """查询账本的历史结算记录。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM settlement WHERE ledger_id = %s "
                "ORDER BY settle_time DESC, settle_id DESC",
                (ledger_id,),
            )
            return [_row_to_settlement(row) for row in cur.fetchall()]


def get_latest(ledger_id: int) -> Optional[Settlement]:
    """查询账本最近一次结算，没有返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM settlement WHERE ledger_id = %s "
                "ORDER BY settle_time DESC, settle_id DESC LIMIT 1",
                (ledger_id,),
            )
            row = cur.fetchone()
            return _row_to_settlement(row) if row else None
