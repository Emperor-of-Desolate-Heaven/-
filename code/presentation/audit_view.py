"""审核页（组件图 UI_Audit）：待审核列表、审核通过/驳回（REQ-006/REQ-007）。

竞争加锁在业务层实现（条件 UPDATE）：两名管理员同时审核同一条记录时，
后到者会收到"该记录正在被其他管理员审核或状态已变化"的提示，
对应时序图"提交与审核"的 alt 分支。
"""

# pylint: disable=duplicate-code  # 成员名单映射与查询页相同

from model.ledger import Ledger
from presentation.console import Session, input_int, input_str, menu, run
from service import audit_service, member_service


def main(session: Session, ledger: Ledger) -> None:
    """审核管理菜单。"""
    menu("审核管理", [
        ("待审核记录列表", lambda: _show_pending(session, ledger)),
        ("审核通过", lambda: _approve(session)),
        ("驳回记录", lambda: _reject(session)),
    ])


def _show_pending(session: Session, ledger: Ledger) -> None:
    ok, records = run(audit_service.list_pending, ledger.ledger_id,
                      session.user_id)
    if not ok:
        return
    if not records:
        print("（暂无待审核记录）")
        return
    names = {
        info.membership.user_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }
    for record in records:
        transfer = ""
        if record.transfer_to:
            transfer = f"【转让申请 → {names.get(record.transfer_to, '?')}】"
        print(f"#{record.record_id} [{record.record_time:%Y-%m-%d %H:%M}] "
              f"{record.category} | {record.reason} | {record.amount} 元"
              f"（{record.direction.value}）"
              f" | 上传人：{names.get(record.submitter_id, '?')} {transfer}")


def _approve(session: Session) -> None:
    record_id = input_int("要审核通过的记录 ID：")
    if not record_id:
        return
    ok, _ = run(audit_service.approve, record_id, session.user_id)
    if ok:
        print(f"记录 #{record_id} 已通过并生效")


def _reject(session: Session) -> None:
    record_id = input_int("要驳回的记录 ID：")
    if not record_id:
        return
    reason = input_str("驳回理由（可留空）：")
    ok, _ = run(audit_service.reject, record_id, session.user_id, reason)
    if ok:
        print(f"记录 #{record_id} 已驳回")
