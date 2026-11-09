"""分摊明细表数据访问（对应类图：分摊明细）。"""

from decimal import Decimal

from dao.db import get_connection
from model.split_item import SplitItem


def _row_to_split(row: dict) -> SplitItem:
    """把查询结果行转换为 SplitItem 实体（FLOAT 经字符串转 Decimal，避免精度误差）。"""
    return SplitItem(
        split_id=row["split_id"],
        record_id=row["record_id"],
        user_id=row["user_id"],
        ratio=Decimal(str(row["ratio"])),
    )


def add_batch(record_id: int, items: list[SplitItem]) -> None:
    """批量写入一条记录的分摊明细。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO split_item (record_id, user_id, ratio) "
                "VALUES (%s, %s, %s)",
                [
                    (record_id, item.user_id, float(item.ratio))
                    for item in items
                ],
            )


def list_by_record(record_id: int) -> list[SplitItem]:
    """查询一条记录的全部分摊明细。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM split_item WHERE record_id = %s "
                "ORDER BY split_id",
                (record_id,),
            )
            return [_row_to_split(row) for row in cur.fetchall()]


def delete_by_record(record_id: int) -> None:
    """删除一条记录的全部分摊明细（重新提交时重建）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM split_item WHERE record_id = %s", (record_id,)
            )
