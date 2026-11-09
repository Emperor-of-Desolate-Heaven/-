"""记录列表与查询（组件图 UI_Query）：四条件组合查询 + 记录详情（REQ-009）。"""

# pylint: disable=duplicate-code  # 成员名单映射与审核页相同

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from model.ledger import Ledger
from model.ledger_record import LedgerRecord
from presentation.console import (Session, input_int, input_str, menu,
                                  pause, run)
from service import member_service, record_service, stats_service


def main(session: Session, ledger: Ledger) -> None:
    """记录查询菜单。"""
    menu("记录查询", [
        ("全部记录", lambda: _show(session, ledger)),
        ("按条件查询", lambda: _query(session, ledger)),
    ])


def _query(session: Session, ledger: Ledger) -> None:
    print("\n-- 组合查询（REQ-009，留空跳过该条件）--")
    category = input_str("类别：")
    names = {
        info.username: info.membership.user_id
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }
    submitter = input_str("上传人用户名：")
    submitter_id = names.get(submitter) if submitter else None
    time_from = _parse_time(input_str("起始时间（年-月-日 时:分）："))
    time_to = _parse_time(input_str("结束时间（年-月-日 时:分）："))
    amount_min = _parse_decimal(input_str("金额下限："))
    amount_max = _parse_decimal(input_str("金额上限："))
    ok, records = run(stats_service.query_records, ledger.ledger_id,
                      session.user_id, category, submitter_id,
                      time_from, time_to, amount_min, amount_max)
    if ok:
        _show(session, ledger, records)


def _parse_time(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        print(f"时间格式无效（{raw}），已忽略该条件")
        return None


def _parse_decimal(raw: str) -> Optional[Decimal]:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        print(f"金额格式无效（{raw}），已忽略该条件")
        return None


def _show(session: Session, ledger: Ledger,
          records: Optional[list] = None) -> None:
    if records is None:
        ok, records = run(stats_service.query_records,
                          ledger.ledger_id, session.user_id)
        if not ok:
            return
    if not records:
        print("（没有符合条件的记录）")
        return
    names = {
        info.membership.user_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }
    for record in records:
        _print_record(record, names)
    detail_id = input_int("输入记录 ID 查看详情（直接回车返回）：")
    if detail_id:
        _detail(ledger, detail_id, names)


def _print_record(record: LedgerRecord, names: dict) -> None:
    transfer = ""
    if record.transfer_to:
        transfer = f"（转让 → {names.get(record.transfer_to, '?')}）"
    print(f"#{record.record_id} [{record.record_time:%Y-%m-%d %H:%M}] "
          f"{record.category} | {record.reason} | {record.amount} 元"
          f"（{record.direction.value}）"
          f" | 上传人：{names.get(record.submitter_id, '?')}"
          f" | {record.status.value}{transfer}")


def _detail(ledger: Ledger, record_id: int, names: dict) -> None:
    record = record_service.get_record(record_id)
    if record is None or record.ledger_id != ledger.ledger_id:
        print("该账本中不存在此记录")
        return
    _print_record(record, names)
    if record.reject_reason:
        print(f"  驳回理由：{record.reject_reason}")
    if record.receipt:
        print(f"  支付凭证：{record.receipt}")
    splits = record_service.get_split_items(record_id)
    if splits:
        print("  分摊明细：")
        for item in splits:
            print(f"    {names.get(item.user_id, '?')}：比例 {item.ratio}，"
                  f"应分摊 {item.share_amount(record.amount)} 元")
    pause()
