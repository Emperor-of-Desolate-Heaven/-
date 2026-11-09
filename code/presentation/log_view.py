"""日志查看页（组件图 UI_Log）：日志查看与访问授权（REQ-015）。

- 管理员（含超管）直接查看日志，查看动作留痕；
- 普通成员须先向管理员申请，审批通过后仅可查看一次，
  再次查看须一天后重新申请；
- 超管另可查看"管理员查看日志"的记录与全部申请/授权记录。
"""

from model.enums import LogOpType
from model.ledger import Ledger
from model.operation_log import OperationLog
from presentation.console import Session, input_int, menu, run
from service import log_service, member_service


def main(session: Session, ledger: Ledger) -> None:
    """日志菜单：按角色显示不同的可用功能。"""
    member = member_service.get_membership(
        ledger.ledger_id, session.user_id
    )
    items = []
    if member.is_admin:
        items += [
            ("查看操作日志", lambda: _view(session, ledger)),
            ("审批日志查看申请", lambda: _review(session, ledger)),
        ]
    else:
        items += [
            ("查看操作日志（需授权）", lambda: _view(session, ledger)),
            ("申请查看日志", lambda: _apply(session, ledger)),
        ]
    if member.is_super_admin:
        items += [
            ("查看“管理员查看日志”的记录",
             lambda: _view_records(session, ledger)),
            ("查看授权/申请记录", lambda: _grants(session, ledger)),
        ]
    menu("日志", items)


def _member_names(session: Session, ledger: Ledger) -> dict:
    """成员 user_id → 用户名 映射（界面显示用）。"""
    return {
        info.membership.user_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }


def _view(session: Session, ledger: Ledger) -> None:
    ok, logs = run(log_service.view_logs, ledger.ledger_id,
                   session.user_id)
    if not ok:
        return
    _print_logs(session, ledger, logs)


def _print_logs(session: Session, ledger: Ledger,
                logs: list[OperationLog]) -> None:
    if not logs:
        print("（暂无日志）")
        return
    names = _member_names(session, ledger)
    for log in logs:
        if log.op_type is LogOpType.VIEW:
            print(f"[{log.log_time:%m-%d %H:%M}] 查看日志 | "
                  f"查看人：{names.get(log.auditor_id, '?')}")
        else:
            print(f"[{log.log_time:%m-%d %H:%M}] {log.op_type.value} | "
                  f"{log.category} | "
                  f"操作人：{names.get(log.auditor_id, '?')} | "
                  f"对象：{names.get(log.submitter_id, '?')}")


def _apply(session: Session, ledger: Ledger) -> None:
    print("\n-- 申请查看日志（REQ-015）--")
    print("可向任一管理员申请，审批通过后仅可查看一次；")
    print("再次查看须一天后重新申请。")
    ok, members = run(member_service.list_members,
                      ledger.ledger_id, session.user_id)
    if not ok:
        return
    admins = [info for info in members if info.membership.is_admin]
    for i, info in enumerate(admins, 1):
        print(f"  {i}. {info.username}（{info.membership.role.value}）")
    idx = input_int("向哪位管理员申请：")
    if not idx or not 1 <= idx <= len(admins):
        print("编号无效")
        return
    ok, _ = run(log_service.request_view, ledger.ledger_id,
                session.user_id, admins[idx - 1].membership.user_id)
    if ok:
        print("已提交申请，等待管理员审批")


def _review(session: Session, ledger: Ledger) -> None:
    ok, applications = run(log_service.list_applications,
                           ledger.ledger_id, session.user_id)
    if not ok:
        return
    if not applications:
        print("（暂无指派给你的待审批申请）")
        return
    names = {
        info.membership.membership_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }
    for i, grant in enumerate(applications, 1):
        print(f"  {i}. 申请人：{names.get(grant.membership_id, '?')}"
              f"（申请时间 {grant.grant_time:%m-%d %H:%M}）")
    idx = input_int("选择申请：")
    if not idx or not 1 <= idx <= len(applications):
        return
    grant_id = applications[idx - 1].grant_id
    choice = input_int("1.通过 2.驳回：")
    if choice == 1:
        ok, _ = run(log_service.approve_request, grant_id,
                    session.user_id)
        if ok:
            print("已批准，申请人可查看日志一次")
    elif choice == 2:
        ok, _ = run(log_service.reject_request, grant_id,
                    session.user_id)
        if ok:
            print("已驳回申请")


def _view_records(session: Session, ledger: Ledger) -> None:
    ok, records = run(log_service.list_view_records, ledger.ledger_id,
                      session.user_id)
    if not ok:
        return
    if not records:
        print("（暂无管理员查看日志的记录）")
        return
    names = _member_names(session, ledger)
    for record in records:
        print(f"[{record.log_time:%m-%d %H:%M}] 查看人："
              f"{names.get(record.auditor_id, '?')}")


def _grants(session: Session, ledger: Ledger) -> None:
    ok, grants = run(log_service.list_grants, ledger.ledger_id,
                     session.user_id)
    if not ok:
        return
    if not grants:
        print("（暂无授权/申请记录）")
        return
    names = {
        info.membership.membership_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }
    admin_names = _member_names(session, ledger)
    for grant in grants:
        used = "已使用" if grant.used else "未使用"
        print(f"#{grant.grant_id} 申请人：{names.get(grant.membership_id, '?')}"
              f" | 审批管理员：{admin_names.get(grant.grant_admin_id, '?')}"
              f" | {grant.status.value} | {used} | "
              f"申请时间 {grant.grant_time:%m-%d %H:%M}")
