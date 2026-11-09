"""创建账本页（组件图 UI_NewLedger）：我的账本列表、创建账本、
申请加入账本（REQ-002 / REQ-003 / REQ-026）。"""

# pylint: disable=duplicate-code  # 本页循环与 console.menu 骨架相似（列表每轮重建）

from model.enums import MembershipStatus
from presentation import home_view
from presentation.console import (Session, input_int, input_str, pause,
                                  run)
from service import ledger_service, member_service


def main(session: Session) -> None:
    """我的账本：列出已参与账本（含待审批申请），可创建账本、申请加入。"""
    while True:
        entries = ledger_service.list_ledgers_with_membership(
            session.user_id
        )
        templates = {
            t.template_id: t.template_type
            for t in ledger_service.list_templates()
        }
        print(f"\n===== 我的账本（{session.username}） =====")
        for i, (ledger, membership) in enumerate(entries, 1):
            status = (
                "" if membership.status is MembershipStatus.ACTIVE
                else "（申请待审批）"
            )
            print(f"  {i}. [#{ledger.ledger_id}] {ledger.name}"
                  f"（{templates.get(ledger.template_id, '?')}）{status}")
        next_no = len(entries) + 1
        print(f"  {next_no}. 创建账本")
        print(f"  {next_no + 1}. 申请加入账本")
        print("  0. 退出登录")
        choice = input_int("请选择：")
        if choice is None:
            continue
        if choice == 0:
            return
        if 1 <= choice <= len(entries):
            ledger, membership = entries[choice - 1]
            if membership.status is not MembershipStatus.ACTIVE:
                print("加入申请待审批，审批通过后即可进入")
                pause()
                continue
            home_view.main(session, ledger)
        elif choice == next_no:
            _create(session)
        elif choice == next_no + 1:
            _apply_join(session)
        else:
            print("无效选项")


def _create(session: Session) -> None:
    print("\n-- 创建账本（REQ-002，必选场景模板）--")
    name = input_str("账本名称：")
    if not name:
        print("账本名称不能为空")
        return
    templates = ledger_service.list_templates()
    for i, template in enumerate(templates, 1):
        print(f"  {i}. {template.template_type}"
              f"（结算：{template.settle_method}；"
              f"默认类别：{'、'.join(template.default_categories)}）")
    choice = input_int("选择场景模板：")
    if not choice or not 1 <= choice <= len(templates):
        print("模板选择无效")
        return
    ok, ledger_id = run(ledger_service.create_ledger, name,
                        templates[choice - 1].template_id, session.user_id)
    if ok:
        print(f"创建成功（账本 #{ledger_id}），"
              "你已自动成为创建者（超级管理员）")


def _apply_join(session: Session) -> None:
    print("\n-- 申请加入账本（REQ-003）--")
    ledger_id = input_int("目标账本 ID（可询问该账本超管）：")
    if not ledger_id:
        return
    ok, _ = run(member_service.apply_join, ledger_id, session.user_id)
    if ok:
        print("已提交加入申请，等待超级管理员审批")
