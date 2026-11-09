"""结算页（组件图 UI_Settle）：执行结算、结算历史（REQ-011/REQ-012）。"""

from datetime import datetime

from model.ledger import Ledger
from presentation.console import Session, input_str, menu, run
from service import ledger_service, settle_service


def main(session: Session, ledger: Ledger) -> None:
    """结算菜单：家庭账本直接提示不结算。"""
    _, template = ledger_service.get_ledger_detail(
        ledger.ledger_id, session.user_id
    )
    if not template.supports_settlement:
        print("家庭账本不结算（REQ-026）")
        return
    menu("结算", [
        ("执行结算", lambda: _do_settle(session, ledger)),
        ("结算历史", lambda: _history(session, ledger)),
    ])


def _do_settle(session: Session, ledger: Ledger) -> None:
    print("\n-- 执行结算 --")
    print("结算时间点取结算当日 0:00，只统计 0:00 前已生效的记录"
          "（REQ-011/REQ-012）；结算期间其他操作一律被拒绝（REQ-012）。")
    raw = input_str("结算日期（年-月-日，回车=今天）：")
    settle_at = datetime.now()
    if raw:
        try:
            settle_at = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            print("日期格式无效")
            return
    ok, settlement = run(settle_service.settle, ledger.ledger_id,
                         session.user_id, settle_at)
    if ok:
        print(f"结算完成：{settlement.settle_time:%Y-%m-%d %H:%M}"
              f"（周期 {settlement.period}）")
        print(f"结果：{settlement.result}")


def _history(session: Session, ledger: Ledger) -> None:
    ok, settlements = run(settle_service.list_settlements,
                          ledger.ledger_id, session.user_id)
    if not ok:
        return
    if not settlements:
        print("（暂无结算记录）")
        return
    for settlement in settlements:
        print(f"#{settlement.settle_id} "
              f"{settlement.settle_time:%Y-%m-%d %H:%M} | "
              f"{settlement.period}")
        print(f"  {settlement.result}")
