"""成员管理页（组件图 UI_Member）：成员列表、加入审批、拉人、角色、
超管转让、可见性、退出/踢人（REQ-001/REQ-003/REQ-022）。"""

from model.enums import Role
from model.ledger import Ledger
from presentation.console import (Session, confirm, input_int, input_str,
                                  menu, run)
from service import ledger_service, member_service


def main(session: Session, ledger: Ledger) -> None:
    """成员管理菜单：按角色显示可用功能（超管功能仅超管可见）。"""
    _, template = ledger_service.get_ledger_detail(
        ledger.ledger_id, session.user_id
    )
    member = member_service.get_membership(
        ledger.ledger_id, session.user_id
    )
    items = [("成员列表", lambda: _list(session, ledger))]
    if member.is_super_admin:
        items += [
            ("审批加入申请", lambda: _review_joins(session, ledger)),
            ("拉人入账本", lambda: _pull_in(session, ledger)),
            ("修改成员角色", lambda: _set_role(session, ledger)),
            ("转让超级管理员", lambda: _transfer_super(session, ledger)),
            ("移除成员", lambda: _remove(session, ledger, kick=True)),
        ]
    if template.template_type == "合租":
        items.append(("我的记录可见性", lambda: _visibility(session, ledger)))
    items.append(("退出账本", lambda: _remove(session, ledger, kick=False)))
    menu("成员管理", items)


def _list(session: Session, ledger: Ledger) -> None:
    ok, members = run(member_service.list_members,
                      ledger.ledger_id, session.user_id)
    if not ok:
        return
    for info in members:
        member = info.membership
        visibility = "可见" if member.visibility_on else "不可见"
        print(f"  {info.username} | {member.role.value} | "
              f"加入时间 {member.join_time:%Y-%m-%d} | 记录{visibility}")
    print("（可见性开关仅合租账本生效，REQ-022）")


def _pick_member(session: Session, ledger: Ledger):
    """列出成员让用户选择一个，返回 MemberInfo 或 None。"""
    ok, members = run(member_service.list_members,
                      ledger.ledger_id, session.user_id)
    if not ok:
        return None
    for i, info in enumerate(members, 1):
        print(f"  {i}. {info.username}（{info.membership.role.value}）")
    idx = input_int("成员编号：")
    if not idx or not 1 <= idx <= len(members):
        print("编号无效")
        return None
    return members[idx - 1]


def _review_joins(session: Session, ledger: Ledger) -> None:
    ok, applications = run(member_service.list_applications,
                           ledger.ledger_id, session.user_id)
    if not ok:
        return
    if not applications:
        print("（暂无待审批的加入申请）")
        return
    for i, info in enumerate(applications, 1):
        membership = info.membership
        print(f"  {i}. {info.username}"
              f"（申请时间 {membership.join_time:%Y-%m-%d %H:%M}）")
    idx = input_int("选择申请：")
    if not idx or not 1 <= idx <= len(applications):
        return
    membership_id = applications[idx - 1].membership.membership_id
    choice = input_int("1.通过 2.驳回：")
    if choice == 1:
        ok, _ = run(member_service.approve_join, membership_id,
                    session.user_id)
        if ok:
            print("已通过，成员加入账本")
    elif choice == 2:
        ok, _ = run(member_service.reject_join, membership_id,
                    session.user_id)
        if ok:
            print("已驳回申请")


def _pull_in(session: Session, ledger: Ledger) -> None:
    username = input_str("要拉入的用户名：")
    if not username:
        return
    ok, _ = run(member_service.pull_in, ledger.ledger_id, username,
                session.user_id)
    if ok:
        print(f"已将 {username} 拉入账本")


def _set_role(session: Session, ledger: Ledger) -> None:
    print("（只能设置普通用户/管理员；超管只能通过身份转让产生）")
    target = _pick_member(session, ledger)
    if target is None:
        return
    role_choice = input_int("新角色（1.普通用户 2.管理员）：")
    new_role = {1: Role.MEMBER, 2: Role.ADMIN}.get(role_choice)
    if new_role is None:
        print("角色无效")
        return
    ok, _ = run(member_service.set_role,
                target.membership.membership_id, new_role, session.user_id)
    if ok:
        print("角色已修改")


def _transfer_super(session: Session, ledger: Ledger) -> None:
    print("（转让后原超管降为普通用户，一个账本始终只有一个超管）")
    target = _pick_member(session, ledger)
    if target is None:
        return
    if not confirm(f"确认将超管身份转让给 {target.username}？"):
        return
    ok, _ = run(member_service.transfer_super_admin,
                ledger.ledger_id, target.membership.user_id, session.user_id)
    if ok:
        print("转让完成，你已降为普通用户")


def _visibility(session: Session, ledger: Ledger) -> None:
    member = member_service.get_membership(
        ledger.ledger_id, session.user_id
    )
    new_on = not member.visibility_on
    label = "开启" if new_on else "关闭"
    if not confirm(f"将你的记录设置为对他人{label}？"):
        return
    ok, _ = run(member_service.set_visibility,
                member.membership_id, new_on, session.user_id)
    if ok:
        print("可见性已更新（对你全部记录生效）")


def _remove(session: Session, ledger: Ledger, kick: bool) -> None:
    """退出账本或超管移除成员（REQ-003 退出清算）。"""
    if kick:
        target = _pick_member(session, ledger)
        if target is None:
            return
        membership_id = target.membership.membership_id
    else:
        membership_id = member_service.get_membership(
            ledger.ledger_id, session.user_id
        ).membership_id
    print("记录处理方式（REQ-003）：")
    print("  1. 默认转让给账本管理员（无管理员则超管）")
    print("  2. 转让给指定成员")
    print("  3. 注销全部记录")
    choice = input_int("选择：")
    if choice == 3:
        ok, _ = run(member_service.remove_member, membership_id,
                    session.user_id, cancel_records=True)
        if ok:
            print("已退出，记录已注销")
        return
    if choice == 1:
        ok, _ = run(member_service.remove_member, membership_id,
                    session.user_id)
        if ok:
            print("已退出，记录已转让")
        return
    if choice == 2:
        target = _pick_member(session, ledger)
        if target is None:
            return
        ok, _ = run(member_service.remove_member, membership_id,
                    session.user_id,
                    transfer_to=target.membership.user_id)
        if ok:
            print("已退出，记录已转让给指定成员")
        return
    print("选择无效")
