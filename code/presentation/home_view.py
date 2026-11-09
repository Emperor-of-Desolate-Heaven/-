"""账本主页（组件图 UI_Home）：统计/红绿灯（REQ-010/REQ-019）、
提交与操作收支记录（REQ-004 ~ REQ-008）、设置预算（REQ-019）。"""

# pylint: disable=duplicate-code  # 本页循环与 console.menu 骨架相似（0=返回账本列表）

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from model.enums import Direction, RecordStatus
from model.ledger import Ledger
from model.ledger_record import LedgerRecord
from model.scene_template import SceneTemplate
from model.split_item import SplitItem
from presentation import (audit_view, log_view, member_view, query_view,
                          settle_view)
from presentation.console import (Session, confirm, input_datetime,
                                  input_int, input_str, menu, run)
from service import (budget_service, ledger_service, member_service,
                     record_service, stats_service)


def main(session: Session, ledger: Ledger) -> None:
    """账本主页循环：顶部统计与红绿灯，下方功能菜单。"""
    while True:
        try:
            ledger, template = ledger_service.get_ledger_detail(
                ledger.ledger_id, session.user_id
            )
            member = member_service.get_membership(
                ledger.ledger_id, session.user_id
            )
        except PermissionError:
            return  # 已退出账本或被移除，回到账本列表
        summary = stats_service.get_summary(
            ledger.ledger_id, session.user_id
        )
        ok, light = run(budget_service.get_traffic_light,
                        ledger.ledger_id, session.user_id)
        light_text = (
            f"预算红绿灯：{light}" if ok and light else "预算红绿灯：未设置预算"
        )
        print(f"\n【{ledger.name}】{template.template_type}账本    "
              f"我的角色：{member.role.value}")
        print(f"生效时间：{summary.effective_time:%Y-%m-%d %H:%M}    "
              f"总支出：{summary.total_expense} 元    "
              f"总收入：{summary.total_income} 元    "
              f"净收支差：{summary.net} 元")
        print(light_text)

        items = [
            ("提交收支记录", lambda: _submit(session, ledger, template)),
            ("记录操作（重新提交/改金额/删除/转让）",
             lambda: _record_ops(session, ledger)),
            ("记录列表与查询", lambda: query_view.main(session, ledger)),
            ("成员管理", lambda: member_view.main(session, ledger)),
            ("结算", lambda: settle_view.main(session, ledger)),
            ("日志查看", lambda: log_view.main(session, ledger)),
        ]
        if member.is_admin:
            items.insert(3, ("审核管理",
                             lambda: audit_view.main(session, ledger)))
        if member.is_super_admin:
            items.append(("设置预算", lambda: _set_budget(session, ledger)))
        for i, (label, _) in enumerate(items, 1):
            print(f"  {i}. {label}")
        print("  0. 返回账本列表")
        choice = input_int("请选择：")
        if choice is None:
            continue
        if choice == 0:
            return
        if 1 <= choice <= len(items):
            items[choice - 1][1]()
        else:
            print("无效选项")


def _submit(session: Session, ledger: Ledger,
            template: SceneTemplate) -> None:
    print("\n-- 提交收支记录（REQ-004/REQ-005）--")
    for i, category in enumerate(template.default_categories, 1):
        print(f"  {i}. {category}")
    choice = input_int("类别（编号）：")
    if not choice or not 1 <= choice <= len(template.default_categories):
        print("类别无效")
        return
    direction_choice = input_int("收支方向（1.支出 2.收入）：")
    if direction_choice == 1:
        direction = Direction.EXPENSE
    elif direction_choice == 2:
        direction = Direction.INCOME
    else:
        print("方向无效")
        return
    amount = input_str("金额：")
    reason = input_str("原因：")
    if not reason:
        print("原因不能为空")
        return
    record_time = input_datetime(
        "发生时间（年-月-日 时:分）：", datetime.now()
    )
    receipt = input_str("支付凭证（可留空）：")
    splits = _input_splits(session, ledger)
    ok, record_id = run(
        record_service.submit_record,
        ledger.ledger_id, session.user_id,
        template.default_categories[choice - 1], reason, amount,
        direction, record_time, receipt, splits,
    )
    if ok:
        print(f"已提交，记录 #{record_id} 待管理员审核")


def _input_splits(
    session: Session, ledger: Ledger
) -> Optional[list[SplitItem]]:
    """输入分摊明细（旅行 AA / 合租按比例，REQ-013/REQ-026）。

    比例之和须为 1；直接回车表示放弃分摊（记录全额归属提交人）。
    """
    if not confirm("需要按比例分摊给多人吗？"):
        return None
    members = member_service.list_members(
        ledger.ledger_id, session.user_id
    )
    print("分摊参与人：")
    for i, info in enumerate(members, 1):
        print(f"  {i}. {info.username}")
    items: list[SplitItem] = []
    used_ids = set()
    total = Decimal("0")
    while True:
        idx = input_int("参与人编号（比例和为 1 时结束，回车放弃分摊）：")
        if idx is None:
            print("已放弃分摊，本记录全额归属提交人")
            return None
        if not 1 <= idx <= len(members):
            print("编号无效")
            continue
        user_id = members[idx - 1].membership.user_id
        if user_id in used_ids:
            print("该成员已添加过")
            continue
        try:
            ratio = Decimal(input_str("分摊比例（0~1，如 0.5）："))
        except InvalidOperation:
            print("请输入数字")
            continue
        if ratio <= 0 or ratio > 1:
            print("比例须在 0~1 之间")
            continue
        items.append(SplitItem(user_id=user_id, ratio=ratio))
        used_ids.add(user_id)
        total += ratio
        print(f"当前比例合计：{total}")
        if total > Decimal("1"):
            print("比例之和超过 1，移除刚添加的参与人")
            items.pop()
            used_ids.discard(user_id)
            total -= ratio
        elif total == Decimal("1"):
            return items


def _record_ops(session: Session, ledger: Ledger) -> None:
    record_id = input_int("记录 ID：")
    if not record_id:
        return
    record = record_service.get_record(record_id)
    if record is None or record.ledger_id != ledger.ledger_id:
        print("该账本中不存在此记录")
        return
    _show_record(session, ledger, record)
    items = []
    if record.status is RecordStatus.REJECTED:
        items.append(("重新提交", lambda: _resubmit(session, ledger, record)))
    if record.status is RecordStatus.ACTIVE:
        items.append(("修改金额", lambda: _modify_amount(session, record)))
        items.append(("删除记录", lambda: _delete(session, record)))
        items.append(("发起转让", lambda: _transfer(session, ledger, record)))
    if not items:
        print("该状态下没有可执行的操作（待审核记录请到审核页处理）")
        return
    menu(f"记录 #{record_id} 操作", items)


def _show_record(session: Session, ledger: Ledger,
                 record: LedgerRecord) -> None:
    names = _member_names(session, ledger)
    transfer = ""
    if record.transfer_to:
        transfer = f"（转让申请 → {names.get(record.transfer_to, '?')}）"
    print(f"#{record.record_id} [{record.record_time:%Y-%m-%d %H:%M}] "
          f"{record.category} | {record.reason} | {record.amount} 元"
          f"（{record.direction.value}）"
          f" | 上传人：{names.get(record.submitter_id, '?')}"
          f" | 状态：{record.status.value}{transfer}")
    if record.reject_reason:
        print(f"驳回理由：{record.reject_reason}")


def _member_names(session: Session, ledger: Ledger) -> dict:
    """成员 user_id → 用户名 映射（界面显示用）。"""
    return {
        info.membership.user_id: info.username
        for info in member_service.list_members(
            ledger.ledger_id, session.user_id
        )
    }


def _resubmit(session: Session, ledger: Ledger,
              record: LedgerRecord) -> None:
    print("\n-- 重新提交（REQ-006/REQ-007：已驳回 → 待审核）--")
    _, template = ledger_service.get_ledger_detail(
        ledger.ledger_id, session.user_id
    )
    for i, category in enumerate(template.default_categories, 1):
        print(f"  {i}. {category}")
    choice = input_int("类别（编号）：")
    if not choice or not 1 <= choice <= len(template.default_categories):
        print("类别无效")
        return
    amount = input_str("金额：")
    reason = input_str("原因：")
    if not reason:
        print("原因不能为空")
        return
    record_time = input_datetime(
        "发生时间（年-月-日 时:分）：", record.record_time
    )
    receipt = input_str("支付凭证（可留空）：")
    ok, _ = run(record_service.resubmit, record.record_id, session.user_id,
                template.default_categories[choice - 1], reason, amount,
                record.direction, record_time, receipt)
    if ok:
        print("已重新提交，等待管理员审核")


def _modify_amount(session: Session, record: LedgerRecord) -> None:
    amount = input_str("新金额：")
    ok, _ = run(record_service.modify_amount, record.record_id, amount,
                session.user_id)
    if ok:
        print("金额已修改（状态不变，无需重新审核，REQ-008）")


def _delete(session: Session, record: LedgerRecord) -> None:
    if not confirm("删除后不可恢复，确认删除？"):
        return
    ok, _ = run(record_service.delete_record, record.record_id,
                session.user_id)
    if ok:
        print("记录已删除")


def _transfer(session: Session, ledger: Ledger,
              record: LedgerRecord) -> None:
    print("\n-- 发起转让（REQ-005：转让并入审核流程）--")
    members = member_service.list_members(
        ledger.ledger_id, session.user_id
    )
    for i, info in enumerate(members, 1):
        print(f"  {i}. {info.username}")
    idx = input_int("转让对象编号：")
    if not idx or not 1 <= idx <= len(members):
        print("编号无效")
        return
    ok, _ = run(record_service.apply_transfer, record.record_id,
                members[idx - 1].membership.user_id, session.user_id)
    if ok:
        print("转让申请已提交，待管理员审核")


def _set_budget(session: Session, ledger: Ledger) -> None:
    amount = input_str("预算金额（留空=取消）：")
    if not amount:
        return
    ok, _ = run(budget_service.set_budget, ledger.ledger_id,
                session.user_id, amount)
    if ok:
        print("预算已设置")
