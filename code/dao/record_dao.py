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
        transfer_to=row["transfer_to_user_id"],
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
                "(ledger_id, submitter_id, transfer_to_user_id, category, "
                " reason, amount, direction, record_time, receipt, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record.ledger_id,
                    record.submitter_id,
                    record.transfer_to,
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
    """无条件更新记录状态（仅测试与内部流程使用）。

    业务状态转换请用条件更新 update_status_if，防止并发下覆盖他人操作。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, reject_reason = %s "
                "WHERE record_id = %s",
                (status.value, reject_reason, record_id),
            )


def update_status_if(
    record_id: int,
    from_status: RecordStatus,
    to_status: RecordStatus,
    reject_reason: Optional[str] = None,
) -> int:
    """条件状态转换（竞争加锁，REQ-007）：仅当记录处于 from_status 时才更新。

    UPDATE 本身是原子操作——多名管理员同时审核同一条记录时，
    只有一人匹配到待审核状态，其他人受影响行数为 0。
    返回受影响行数（1=转换成功，0=已被他人处理）。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, reject_reason = %s "
                "WHERE record_id = %s AND status = %s",
                (to_status.value, reject_reason, record_id, from_status.value),
            )
            return cur.rowcount


def set_transfer(record_id: int, transfer_to: int) -> int:
    """发起转让申请（REQ-005）：已生效 → 待审核，并暂存转让目标。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, "
                "transfer_to_user_id = %s, reject_reason = NULL "
                "WHERE record_id = %s AND status = %s",
                (
                    RecordStatus.PENDING.value,
                    transfer_to,
                    record_id,
                    RecordStatus.ACTIVE.value,
                ),
            )
            return cur.rowcount


def approve_if_pending(record_id: int) -> int:
    """审核通过（竞争加锁）：待审核 → 已生效。

    若该记录是转让申请（transfer_to 非空），同一事务内把上传人改为
    转让目标并清空转让标记。返回 1=成功，0=记录已不是待审核（已被他人处理）。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, reject_reason = NULL "
                "WHERE record_id = %s AND status = %s",
                (RecordStatus.ACTIVE.value, record_id,
                 RecordStatus.PENDING.value),
            )
            if cur.rowcount == 0:
                return 0
            cur.execute(
                "UPDATE ledger_record SET submitter_id = transfer_to_user_id, "
                "transfer_to_user_id = NULL "
                "WHERE record_id = %s AND transfer_to_user_id IS NOT NULL",
                (record_id,),
            )
            return 1


def update_amount(record_id: int, amount: Decimal) -> None:
    """修改记录金额（修改金额不改变状态、无需重新审核，REQ-008）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET amount = %s WHERE record_id = %s",
                (amount, record_id),
            )


def update_submitter_by_owner(
    ledger_id: int, old_user_id: int, new_user_id: int
) -> int:
    """把某成员的全部未删除记录转让给另一成员（REQ-003 退出时记录转让）。

    已删除的记录不随转让。返回转让的记录条数。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET submitter_id = %s "
                "WHERE ledger_id = %s AND submitter_id = %s "
                "AND status <> %s",
                (
                    new_user_id,
                    ledger_id,
                    old_user_id,
                    RecordStatus.DELETED.value,
                ),
            )
            return cur.rowcount


def reject_all_pending_by_submitter(
    ledger_id: int, user_id: int, reason: str
) -> int:
    """把某成员的全部待审核记录改为已驳回（REQ-003：退出成员存在待审核记录时直接审核失败）。

    返回处理的记录条数。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s, reject_reason = %s "
                "WHERE ledger_id = %s AND submitter_id = %s AND status = %s",
                (
                    RecordStatus.REJECTED.value,
                    reason,
                    ledger_id,
                    user_id,
                    RecordStatus.PENDING.value,
                ),
            )
            return cur.rowcount


def delete_all_by_submitter(ledger_id: int, user_id: int) -> int:
    """把某成员的全部未删除记录注销（REQ-003 退出时选择注销记录）。

    返回处理的记录条数。
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ledger_record SET status = %s "
                "WHERE ledger_id = %s AND submitter_id = %s AND status <> %s",
                (
                    RecordStatus.DELETED.value,
                    ledger_id,
                    user_id,
                    RecordStatus.DELETED.value,
                ),
            )
            return cur.rowcount


def update_fields(  # pylint: disable=too-many-arguments, too-many-positional-arguments
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
                "status = %s, reject_reason = NULL, "
                "transfer_to_user_id = NULL WHERE record_id = %s",
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


def query(  # pylint: disable=too-many-arguments, too-many-positional-arguments
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


def list_active_between(
    ledger_id: int,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
) -> list[LedgerRecord]:
    """查询时间区间内的已生效记录（REQ-011/REQ-012 结算统计用）。

    仅已生效记录参与结算；time_to 为开区间（结算时间点 0:00 的记录
    不计入，REQ-012"只统计 0:00 前已生效的记录"）。
    """
    sql = ("SELECT * FROM ledger_record "
           "WHERE ledger_id = %s AND status = %s")
    params: list = [ledger_id, RecordStatus.ACTIVE.value]
    if time_from is not None:
        sql += " AND record_time >= %s"
        params.append(time_from)
    if time_to is not None:
        sql += " AND record_time < %s"
        params.append(time_to)
    sql += " ORDER BY record_time, record_id"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [_row_to_record(row) for row in cur.fetchall()]


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
