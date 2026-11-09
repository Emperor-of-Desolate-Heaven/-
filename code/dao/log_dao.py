"""操作日志表数据访问（对应类图：操作日志）。"""

from dao.db import get_connection
from model.enums import LogOpType
from model.operation_log import OperationLog


def _row_to_log(row: dict) -> OperationLog:
    """把查询结果行转换为 OperationLog 实体。"""
    return OperationLog(
        log_id=row["log_id"],
        ledger_id=row["ledger_id"],
        op_type=LogOpType(row["op_type"]),
        category=row["category"] or "",
        auditor_id=row["auditor_id"],
        submitter_id=row["submitter_id"],
        log_time=row["log_time"],
    )


def add(log: OperationLog) -> int:
    """新增一条操作日志（REQ-015 操作留痕）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO operation_log "
                "(ledger_id, op_type, category, auditor_id, submitter_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    log.ledger_id,
                    log.op_type.value,
                    log.category,
                    log.auditor_id,
                    log.submitter_id,
                ),
            )
            return cur.lastrowid


def list_by_ledger(ledger_id: int) -> list[OperationLog]:
    """查询账本的全部操作日志。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM operation_log WHERE ledger_id = %s "
                "ORDER BY log_time DESC, log_id DESC",
                (ledger_id,),
            )
            return [_row_to_log(row) for row in cur.fetchall()]


def list_by_type(
    ledger_id: int, op_type: LogOpType
) -> list[OperationLog]:
    """按类型查询账本日志（如"查看日志"记录，供超管查看，REQ-015）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM operation_log "
                "WHERE ledger_id = %s AND op_type = %s "
                "ORDER BY log_time DESC, log_id DESC",
                (ledger_id, op_type.value),
            )
            return [_row_to_log(row) for row in cur.fetchall()]
