"""收支记录表数据访问（对应类图：收支记录）。"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from dao.db import get_connection
from model.enums import Direction, RecordStatus
from model.ledger_record import LedgerRecord


def _row_to_record(row: dict) -> LedgerRecord:
    """把查询结果行转换为 LedgerRecord 实体。"""
    return LedgerRecord(
        record_id=row["record_id"],
        ledger_id=row["ledger_id"],
        submitter_id=row["submitter_id"],
        category=row["category"],
        reason=row["reason"],
        amount=row["amount"],
        direction=Direction(row["direction"]),
        record_time=row["record_time"],
        receipt=row["receipt"] or "",
        status=RecordStatus(row["status"]),
        reject_reason=row["reject_reason"] or "",
    )


def add(record: LedgerRecord) -> int:
    """新增收支记录，返回记录 ID。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ledger_record "
                "(ledger_id, submitter_id, category, reason, amount, "
                " direction, record_time, receipt, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record.ledger_id,
                    record.submitter_id,
                    record.category,
                    record.reason,
                    record.amount,
                    record.direction.value,
                    record.record_time,
                    record.receipt,
                    record.status.value,
                ),
            )
            return cur.lastrowid


def get_by_id(record_id: int) -> Optional[LedgerRecord]:
    """按记录 ID 查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ledger_record WHERE record_id = %s",
                (record_id,),
            )
            row = cur.fetchone()
            return _row_to_record(row) if row else None


def list_by_ledger(
    ledger_id: int, include_deleted: bool = False
) -> list[LedgerRecord]:
    """查询账本的记录列表；默认不含已删除记录（REQ-022）。"""
    sql = "SELECT * FROM ledger_record WHERE ledger_id = %s"
    if not include_deleted:
        sql += " AND status <> %s"
    sql += " ORDER BY record_time DESC, record_id DESC"
    params = (
        (ledger_id,)
        if include_deleted
        else (ledger_id, RecordStatus.DELETED.value)
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [_row_to_record(row) for row in cur.fetchall()]


def list_by_status(
    ledger_id: int, status: RecordStatus
) -> list[LedgerRecord]:
    """按状态查询账本记录（如待审核列表）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ledger_record "
                "WHERE ledger_id = %s AND status = %s ORDER BY record_id",
                (ledger_id, status.value),
            )
            return [_row_to_record(row) for row in cur.fetchall()]


def update_status(
    record_id: int,
    status: RecordStatus,
    reject_reason: Optional[str] = None,
) -> None:
    """更新记录状态，可同时写入驳回理由（REQ-006、REQ-007）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, reject_reason = %s "
                "WHERE record_id = %s",
                (status.value, reject_reason, record_id),
            )


def update_amount(record_id: int, amount: Decimal) -> None:
    """修改记录金额（修改金额不改变状态、无需重新审核，REQ-008）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET amount = %s WHERE record_id = %s",
                (amount, record_id),
            )


def update_fields(
    record_id: int,
    category: str,
    reason: str,
    amount: Decimal,
    direction: Direction,
    record_time: datetime,
    receipt: str,
) -> None:
    """重新提交时更新记录内容并恢复为待审核（REQ-007）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET category = %s, reason = %s, "
                "amount = %s, direction = %s, record_time = %s, receipt = %s, "
                "status = %s, reject_reason = NULL WHERE record_id = %s",
                (
                    category,
                    reason,
                    amount,
                    direction.value,
                    record_time,
                    receipt,
                    RecordStatus.PENDING.value,
                    record_id,
                ),
            )


def exists_duplicate(
    ledger_id: int,
    reason: str,
    record_time: datetime,
    receipt: str,
    exclude_id: Optional[int] = None,
) -> bool:
    """查重：除金额外其他三项（原因、时间、凭证）相同即视为疑似重复（REQ-014）。

    已删除的记录不参与查重。
    """
    sql = (
        "SELECT COUNT(*) AS cnt FROM ledger_record "
        "WHERE ledger_id = %s AND reason = %s AND record_time = %s "
        "AND IFNULL(receipt, '') = %s AND status <> %s"
    )
    params: tuple = (
        ledger_id,
        reason,
        record_time,
        receipt,
        RecordStatus.DELETED.value,
    )
    if exclude_id is not None:
        sql += " AND record_id <> %s"
        params += (exclude_id,)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()["cnt"] > 0


def query(
    ledger_id: int,
    category: Optional[str] = None,
    submitter_id: Optional[int] = None,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
    amount_min: Optional[Decimal] = None,
    amount_max: Optional[Decimal] = None,
) -> list[LedgerRecord]:
    """多条件组合查询记录（REQ-009）：类别、成员、时间范围、金额区间可任意组合。"""
    sql = "SELECT * FROM ledger_record WHERE ledger_id = %s AND status <> %s"
    params: list = [ledger_id, RecordStatus.DELETED.value]
    if category:
        sql += " AND category = %s"
        params.append(category)
    if submitter_id:
        sql += " AND submitter_id = %s"
        params.append(submitter_id)
    if time_from:
        sql += " AND record_time >= %s"
        params.append(time_from)
    if time_to:
        sql += " AND record_time <= %s"
        params.append(time_to)
    if amount_min is not None:
        sql += " AND amount >= %s"
        params.append(amount_min)
    if amount_max is not None:
        sql += " AND amount <= %s"
        params.append(amount_max)
    sql += " ORDER BY record_time DESC, record_id DESC"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [_row_to_record(row) for row in cur.fetchall()]


def sum_by_direction(ledger_id: int, direction: Direction) -> Decimal:
    """汇总账本某方向（收入/支出）的已生效记录总额，无记录返回 0（REQ-010）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT IFNULL(SUM(amount), 0) AS total FROM ledger_record "
                "WHERE ledger_id = %s AND direction = %s AND status = %s",
                (ledger_id, direction.value, RecordStatus.ACTIVE.value),
            )
            row = cur.fetchone()
            return Decimal(row["total"])


def count_by_status(ledger_id: int, status: RecordStatus) -> int:
    """统计账本内某状态的记录条数（结算结果展示用）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM ledger_record "
                "WHERE ledger_id = %s AND status = %s",
                (ledger_id, status.value),
            )
            return cur.fetchone()["cnt"]
