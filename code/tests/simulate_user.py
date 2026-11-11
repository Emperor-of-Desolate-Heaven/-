"""模拟用户测试：两个虚拟用户通过真实命令行界面走完整业务流程。

模拟过程（全部通过 presentation 层菜单操作，等价于真人输入）：
  Alice 注册 → Bob 注册 → Alice 创建旅行账本并提交两笔支出 →
  Bob 申请加入 → Alice 审批加入、审核记录、设置预算、执行结算 →
  Bob 申请日志查看授权 → Alice 审批并查看日志 → Bob 使用授权查看一次。

运行（在 code 目录下）：
    py -3.13 tests/simulate_user.py
所有测试数据使用 sim_lab3_ 前缀，脚本结束（含失败）自动清理。
"""

# pylint: disable=wrong-import-position  # 先补 sys.path 再导入项目模块

import builtins
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dao import (budget_dao, grant_dao, log_dao,  # noqa: E402
                 membership_dao, record_dao, settlement_dao)
from model.enums import GrantStatus, LogOpType, MembershipStatus, \
    RecordStatus  # noqa: E402
from presentation import login_view  # noqa: E402
from service import auth_service, ledger_service  # noqa: E402
from tests.support import cleanup_test_data, unique_name  # noqa: E402

PREFIX = "sim_lab3_"
PASSWORD = "pw123456"


class ScriptedInput:  # pylint: disable=too-few-public-methods
    """按脚本逐条返回输入值的 input() 替身。"""

    def __init__(self, steps, label):
        self.steps = list(steps)
        self.label = label

    def __call__(self, prompt=""):
        if not self.steps:
            raise AssertionError(
                f"[{self.label}] 脚本输入耗尽，最后提示：{prompt}"
            )
        return self.steps.pop(0)


def run_session(label, steps):
    """执行一次命令行会话（一个用户从进入系统到退出），返回屏幕输出。"""
    scripted = ScriptedInput(steps, label)
    buffer = io.StringIO()
    original_input = builtins.input
    builtins.input = scripted
    try:
        with redirect_stdout(buffer):
            try:
                login_view.main()
            except SystemExit:
                pass
    finally:
        builtins.input = original_input
    output = buffer.getvalue()
    if scripted.steps:
        raise AssertionError(
            f"[{label}] 还有未消耗的输入：{scripted.steps}"
        )
    print(f"[会话完成] {label}")
    return output


def check(condition, message):
    """断言并在成功时打印 PASS。"""
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def main():  # pylint: disable=too-many-locals
    """模拟两个用户的完整使用流程并核对数据库结果。"""
    cleanup_test_data(PREFIX)
    alice_name = unique_name("alice", PREFIX)
    bob_name = unique_name("bob", PREFIX)
    ledger_name = "模拟旅行账本" + datetime.now().strftime("%H%M%S")
    try:
        run_session("注册 Alice", [
            "2", alice_name, PASSWORD, PASSWORD, "0",
        ])
        run_session("注册 Bob", [
            "2", bob_name, PASSWORD, PASSWORD, "0",
        ])

        output = run_session("Alice 创建账本并提交两笔支出", [
            "1", alice_name, PASSWORD,     # 登录
            "1", ledger_name, "1",         # 创建账本（模板 1 = 旅行）
            "1",                           # 进入账本主页
            "1", "1", "1", "100", "午餐", "", "", "n",  # 提交支出 100
            "1", "2", "1", "200", "住宿", "", "", "n",  # 提交支出 200
            "0", "0", "0",                 # 回账本列表 → 退出登录 → 退出
        ])
        check("创建成功" in output and output.count("已提交") == 2,
              "Alice 通过界面创建账本并提交两笔支出")

        alice = auth_service.login(alice_name, PASSWORD)
        bob = auth_service.login(bob_name, PASSWORD)
        ledger_id = next(
            ledger.ledger_id
            for ledger, _ in ledger_service.list_ledgers_with_membership(
                alice.user_id)
            if ledger.name == ledger_name
        )
        pending = record_dao.list_by_status(
            ledger_id, RecordStatus.PENDING
        )
        record_ids = [record.record_id for record in pending]
        check(len(record_ids) == 2, "两笔记录初始状态为待审核")

        run_session("Bob 申请加入账本", [
            "1", bob_name, PASSWORD,
            "2", str(ledger_id),           # 申请加入
            "0", "0",                      # 退出登录 → 退出
        ])
        bob_membership = membership_dao.get(ledger_id, bob.user_id)
        check(bob_membership.status is MembershipStatus.PENDING,
              "Bob 的加入申请处于待审批状态")

        settle_date = (datetime.now() + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        output = run_session("Alice 审批加入/审核记录/设预算/结算", [
            "1", alice_name, PASSWORD,
            "1",                           # 进入账本
            "5", "2", "1", "1", "0",       # 成员管理 → 审批通过 Bob
            "4", "2", str(record_ids[0]),  # 审核管理 → 通过第一笔
            "2", str(record_ids[1]), "0",  # 通过第二笔 → 返回主页
            "8", "500",                    # 设置预算 500
            "6", "1", settle_date, "0",    # 结算（取明日 0:00 为界）
            "0", "0", "0",
        ])
        check("结算完成" in output, "Alice 完成成员审批、记录审核、预算与结算")

        bob_membership = membership_dao.get(ledger_id, bob.user_id)
        check(bob_membership.status is MembershipStatus.ACTIVE,
              "Bob 已成为账本正式成员")
        active_records = record_dao.list_active_between(ledger_id)
        check(len(active_records) == 2, "两笔记录均已生效")
        budget = budget_dao.get_by_ledger(ledger_id)
        check(budget is not None and str(budget.amount) == "500.00",
              "预算 500 元已保存")
        settlements = settlement_dao.list_by_ledger(ledger_id)
        check(len(settlements) == 1, "产生一条结算记录")
        check("总支出 300.00 元" in settlements[0].result
              and "记录 2 条" in settlements[0].result,
              "结算结果统计正确（支出 300 元、2 条记录）")

        output = run_session("Bob 申请日志查看授权", [
            "1", bob_name, PASSWORD,
            "1",                           # 进入账本
            "6",                           # 日志查看
            "1",                           # 无授权查看 → 预期被拒绝
            "2", "1",                      # 申请 → 选择管理员
            "0", "0", "0", "0",
        ])
        check("无有效授权" in output, "Bob 无授权查看日志被拒绝")
        grants = grant_dao.list_by_ledger(ledger_id)
        check(len(grants) == 1 and grants[0].status is GrantStatus.PENDING,
              "日志查看申请已提交，等待审批")

        output = run_session("Alice 审批日志申请并查看日志", [
            "1", alice_name, PASSWORD,
            "1",
            "7",                           # 日志查看
            "2", "1", "1",                 # 审批日志申请 → 通过
            "1",                           # 管理员查看日志（留痕）
            "3",                           # 查看"管理员查看日志"记录
            "4",                           # 查看授权/申请记录
            "0", "0", "0", "0",
        ])
        check("已批准" in output, "Alice 审批通过日志查看申请")

        output = run_session("Bob 使用授权查看日志（一次有效）", [
            "1", bob_name, PASSWORD,
            "1",
            "6",                           # 日志查看
            "1",                           # 第一次查看成功
            "1",                           # 第二次查看 → 预期被拒绝
            "0", "0", "0", "0",
        ])
        check("无有效授权" in output, "授权一次有效，第二次查看被拒绝")
        grants = grant_dao.list_by_ledger(ledger_id)
        check(grants[0].used, "授权已标记为已使用")
        view_logs = log_dao.list_by_type(ledger_id, LogOpType.VIEW)
        check(len(view_logs) >= 1, "管理员查看日志动作已留痕")

        print("\n全部模拟用户流程通过。")
    finally:
        cleanup_test_data(PREFIX)
        print("测试数据已清理。")


if __name__ == "__main__":
    main()
