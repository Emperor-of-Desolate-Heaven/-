"""账号/账本基础流程 + 记录状态机、权限与竞争加锁集成测试。

运行（在 code 目录下）：py -3.13 -m unittest tests.test_record_flow -v
"""

import unittest
from datetime import datetime
from decimal import Decimal

from dao import ledger_dao, membership_dao, record_dao, template_dao
from model.enums import Direction, RecordStatus, Role
from model.split_item import SplitItem
from service import (audit_service, auth_service, ledger_service,
                     member_service, record_service, settle_service,
                     stats_service)
from tests.support import DEFAULT_PASSWORD, DbTestCase, unique_name


class AuthAndLedgerTest(DbTestCase):
    """REQ-020 注册登录 + REQ-002 账本创建。"""

    def test_register_and_login(self):
        """注册成功、密码哈希存储、登录校验。"""
        user = self.make_user("auth")
        self.assertNotEqual(user.password, DEFAULT_PASSWORD)
        self.assertEqual(len(user.password), 64)  # SHA-256 十六进制
        logged = auth_service.login(user.username, DEFAULT_PASSWORD)
        self.assertEqual(logged.user_id, user.user_id)
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_service.login(user.username, "wrong-password")

    def test_register_validation(self):
        """用户名重复、用户名/密码为空均被拒绝。"""
        user = self.make_user("dup")
        with self.assertRaisesRegex(ValueError, "用户名已存在"):
            auth_service.register(user.username, DEFAULT_PASSWORD)
        with self.assertRaisesRegex(ValueError, "用户名不能为空"):
            auth_service.register("   ", "pw")
        with self.assertRaisesRegex(ValueError, "密码不能为空"):
            auth_service.register(unique_name("empty"), "")

    def test_create_ledger_and_creator_role(self):
        """创建账本：名称必填、模板必须存在、创建者自动成为超管。"""
        creator = self.make_user("lg")
        template = template_dao.get_by_type("旅行")
        with self.assertRaisesRegex(ValueError, "账本名称不能为空"):
            ledger_service.create_ledger("  ", template.template_id,
                                         creator.user_id)
        with self.assertRaisesRegex(ValueError, "场景模板不存在"):
            ledger_service.create_ledger("测试账本", 999999,
                                         creator.user_id)
        ledger_id, _ = self.make_ledger(creator, "旅行")
        member = membership_dao.get(ledger_id, creator.user_id)
        self.assertIs(member.role, Role.CREATOR)
        self.assertTrue(member.is_super_admin)
        ledgers = ledger_service.list_ledgers_with_membership(
            creator.user_id
        )
        self.assertIn(ledger_id, [ledger.ledger_id for ledger, _ in ledgers])


class RecordSubmitTest(DbTestCase):
    """REQ-004/REQ-005/REQ-013/REQ-014 记录提交校验。"""

    def setUp(self):
        self.creator = self.make_user("c")
        self.member = self.make_user("m")
        self.ledger_id, self.template = self.make_ledger(self.creator)
        member_service.pull_in(self.ledger_id, self.member.username,
                               self.creator.user_id)

    def test_submit_success_is_pending(self):
        """提交成功后记录为待审核，金额与方向正确落库。"""
        record_id = self.submit(self.ledger_id, self.member, self.template)
        record = record_service.get_record(record_id)
        self.assertIs(record.status, RecordStatus.PENDING)
        self.assertEqual(record.amount, Decimal("100.00"))
        self.assertIs(record.direction, Direction.EXPENSE)
        self.assertEqual(record.submitter_id, self.member.user_id)

    def test_invalid_amounts_rejected(self):
        """非数字、零、负数、超上限一律拒绝（REQ-013）。"""
        cases = [
            ("abc", "金额必须是数字"),
            ("0", "金额必须大于 0"),
            ("-5", "金额必须大于 0"),
            ("99999999999", "金额超出允许范围"),
        ]
        for amount, message in cases:
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValueError, message):
                    self.submit(self.ledger_id, self.member, self.template,
                                amount=amount)

    def test_empty_reason_rejected(self):
        """原因不能为空。"""
        with self.assertRaisesRegex(ValueError, "原因不能为空"):
            self.submit(self.ledger_id, self.member, self.template,
                        reason="   ")

    def test_category_must_come_from_template(self):
        """类别必须是当前模板默认类别之一（REQ-026）。"""
        with self.assertRaisesRegex(ValueError, "类别必须是该模板的默认类别"):
            self.submit(self.ledger_id, self.member, self.template,
                        category="不存在的类别")

    def test_non_member_cannot_submit(self):
        """非成员不能提交记录。"""
        outsider = self.make_user("out")
        with self.assertRaisesRegex(PermissionError, "你不是该账本的成员"):
            self.submit(self.ledger_id, outsider, self.template)

    def test_duplicate_submission_rejected(self):
        """原因、时间、凭证相同视为重复提交（REQ-014）。"""
        moment = datetime.now().replace(microsecond=0)
        self.submit(self.ledger_id, self.member, self.template,
                    reason="同一条", record_time=moment, receipt="凭证A")
        with self.assertRaisesRegex(ValueError, "疑似重复提交"):
            self.submit(self.ledger_id, self.member, self.template,
                        reason="同一条", record_time=moment, receipt="凭证A")

    def test_split_items_saved_and_validated(self):
        """分摊明细保存；比例和不为 1、非成员、非正比例均拒绝（REQ-013）。"""
        items = [
            SplitItem(user_id=self.creator.user_id, ratio=Decimal("0.6")),
            SplitItem(user_id=self.member.user_id, ratio=Decimal("0.4")),
        ]
        record_id = self.submit(self.ledger_id, self.member, self.template,
                                split_items=items)
        saved = record_service.get_split_items(record_id)
        self.assertEqual(
            sorted(str(item.ratio) for item in saved), ["0.4", "0.6"]
        )
        outsider = self.make_user("s")
        bad_cases = [
            ([SplitItem(user_id=self.member.user_id,
                        ratio=Decimal("0.5"))], "分摊比例之和必须为 1"),
            ([SplitItem(user_id=outsider.user_id,
                        ratio=Decimal("1"))], "分摊参与人必须是账本成员"),
            ([SplitItem(user_id=self.member.user_id,
                        ratio=Decimal("0"))], "分摊比例必须大于 0"),
        ]
        for split_items, message in bad_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.submit(self.ledger_id, self.member, self.template,
                                split_items=split_items)


class RecordLifecycleTest(DbTestCase):
    """REQ-006/REQ-007/REQ-008 状态机流转、权限与竞争加锁。"""

    def setUp(self):
        self.approver = self.make_user("admin")   # 创建者，超管
        self.submitter = self.make_user("sub")    # 普通成员
        self.other = self.make_user("other")      # 普通成员
        self.ledger_id, self.template = self.make_ledger(self.approver)
        for user in (self.submitter, self.other):
            member_service.pull_in(self.ledger_id, user.username,
                                   self.approver.user_id)

    def _submit(self, **kwargs):
        return self.submit(self.ledger_id, self.submitter, self.template,
                           **kwargs)

    def test_pending_to_active_and_stats(self):
        """待审核 → 已生效，统计随之更新（REQ-010/REQ-017）。"""
        record_id = self._submit(amount="100")
        before = stats_service.get_summary(
            self.ledger_id, self.approver.user_id
        )
        self.assertEqual(before.total_expense, Decimal("0"))
        audit_service.approve(record_id, self.approver.user_id)
        after = stats_service.get_summary(
            self.ledger_id, self.approver.user_id
        )
        self.assertEqual(after.total_expense, Decimal("100.00"))
        self.assertIs(record_service.get_record(record_id).status,
                      RecordStatus.ACTIVE)

    def test_reject_then_resubmit(self):
        """待审核 → 已驳回 → 重新提交 → 待审核 → 已生效（REQ-006/REQ-007）。"""
        record_id = self._submit(amount="100")
        audit_service.reject(record_id, self.approver.user_id, "票据不清")
        rejected = record_service.get_record(record_id)
        self.assertIs(rejected.status, RecordStatus.REJECTED)
        self.assertEqual(rejected.reject_reason, "票据不清")
        record_service.resubmit(
            record_id, self.submitter.user_id,
            self.template.default_categories[0], "补充后的原因", "120",
            Direction.EXPENSE, datetime.now(), "",
        )
        resubmitted = record_service.get_record(record_id)
        self.assertIs(resubmitted.status, RecordStatus.PENDING)
        self.assertEqual(resubmitted.amount, Decimal("120.00"))
        audit_service.approve(record_id, self.approver.user_id)
        self.assertIs(record_service.get_record(record_id).status,
                      RecordStatus.ACTIVE)

    def test_resubmit_permissions_and_states(self):
        """仅提交人本人、仅已驳回记录可重新提交。"""
        record_id = self._submit()
        with self.assertRaisesRegex(ValueError, "当前状态不能重新提交"):
            record_service.resubmit(
                record_id, self.submitter.user_id,
                self.template.default_categories[0], "原因", "100",
                Direction.EXPENSE, datetime.now(), "",
            )
        audit_service.reject(record_id, self.approver.user_id)
        with self.assertRaisesRegex(PermissionError, "仅提交人本人可重新提交"):
            record_service.resubmit(
                record_id, self.other.user_id,
                self.template.default_categories[0], "原因", "100",
                Direction.EXPENSE, datetime.now(), "",
            )

    def test_approve_requires_admin_and_pending(self):
        """普通成员不能审核；非待审核记录不能再次审核。"""
        record_id = self._submit()
        with self.assertRaisesRegex(PermissionError, "仅管理员可审核记录"):
            audit_service.approve(record_id, self.submitter.user_id)
        audit_service.approve(record_id, self.approver.user_id)
        with self.assertRaisesRegex(ValueError, "仅待审核记录可审核"):
            audit_service.approve(record_id, self.approver.user_id)

    def test_concurrent_approve_conditional_lock(self):
        """条件 UPDATE 竞争锁：同一记录只有第一次审核成功（时序图 alt 分支）。"""
        record_id = self._submit()
        self.assertEqual(record_dao.approve_if_pending(record_id), 1)
        self.assertEqual(record_dao.approve_if_pending(record_id), 0)

    def test_reject_active_and_rejected_after_delete(self):
        """已生效可驳回（统计回退）；已删除不可再驳回。"""
        record_id = self._submit()
        audit_service.approve(record_id, self.approver.user_id)
        audit_service.reject(record_id, self.approver.user_id, "事后发现问题")
        self.assertIs(record_service.get_record(record_id).status,
                      RecordStatus.REJECTED)

        deleted_id = self._submit()
        audit_service.approve(deleted_id, self.approver.user_id)
        record_service.delete_record(deleted_id, self.approver.user_id)
        with self.assertRaisesRegex(ValueError, "当前状态不能驳回"):
            audit_service.reject(deleted_id, self.approver.user_id)

    def test_modify_amount(self):
        """仅管理员、仅已生效记录可修改金额，修改后状态不变（REQ-008）。"""
        record_id = self._submit(amount="100")
        audit_service.approve(record_id, self.approver.user_id)
        with self.assertRaisesRegex(PermissionError, "仅管理员可执行该操作"):
            record_service.modify_amount(
                record_id, "150", self.submitter.user_id
            )
        record_service.modify_amount(
            record_id, "150", self.approver.user_id
        )
        modified = record_service.get_record(record_id)
        self.assertEqual(modified.amount, Decimal("150.00"))
        self.assertIs(modified.status, RecordStatus.ACTIVE)

    def test_modify_rejects_invalid_amount_and_pending(self):
        """修改金额同样走金额校验；待审核记录不可修改。"""
        record_id = self._submit()
        with self.assertRaisesRegex(ValueError, "仅已生效记录可修改金额"):
            record_service.modify_amount(
                record_id, "150", self.approver.user_id
            )
        audit_service.approve(record_id, self.approver.user_id)
        with self.assertRaisesRegex(ValueError, "金额必须大于 0"):
            record_service.modify_amount(
                record_id, "0", self.approver.user_id
            )

    def test_delete_record(self):
        """仅管理员可删除已生效记录，删除后不可重复删除（REQ-008）。"""
        record_id = self._submit()
        audit_service.approve(record_id, self.approver.user_id)
        with self.assertRaisesRegex(PermissionError, "仅管理员可执行该操作"):
            record_service.delete_record(record_id, self.submitter.user_id)
        record_service.delete_record(record_id, self.approver.user_id)
        self.assertIs(record_service.get_record(record_id).status,
                      RecordStatus.DELETED)
        with self.assertRaisesRegex(ValueError, "仅已生效记录可删除"):
            record_service.delete_record(record_id, self.approver.user_id)

    def test_transfer_joins_audit_flow(self):
        """转让申请：仅本人可发起，审核通过后上传人变更（REQ-005/REQ-007）。"""
        record_id = self._submit()
        audit_service.approve(record_id, self.approver.user_id)
        with self.assertRaisesRegex(PermissionError, "仅提交人本人可发起转让"):
            record_service.apply_transfer(
                record_id, self.other.user_id, self.approver.user_id
            )
        outsider = self.make_user("x")
        with self.assertRaisesRegex(ValueError, "转让对象必须是该账本的已生效成员"):
            record_service.apply_transfer(
                record_id, outsider.user_id, self.submitter.user_id
            )
        record_service.apply_transfer(
            record_id, self.other.user_id, self.submitter.user_id
        )
        pending = record_service.get_record(record_id)
        self.assertIs(pending.status, RecordStatus.PENDING)
        self.assertEqual(pending.transfer_to, self.other.user_id)
        audit_service.approve(record_id, self.approver.user_id)
        transferred = record_service.get_record(record_id)
        self.assertIs(transferred.status, RecordStatus.ACTIVE)
        self.assertEqual(transferred.submitter_id, self.other.user_id)

    def test_settling_lock_blocks_mutations(self):
        """结算锁期间所有修改类操作被拒绝（REQ-012）。"""
        pending_id = self._submit()
        active_id = self._submit()
        audit_service.approve(active_id, self.approver.user_id)
        ledger_dao.set_settling(self.ledger_id, True)
        try:
            cases = [
                self._submit,
                lambda: audit_service.approve(pending_id,
                                              self.approver.user_id),
                lambda: audit_service.reject(pending_id,
                                             self.approver.user_id),
                lambda: record_service.modify_amount(
                    active_id, "88", self.approver.user_id),
                lambda: record_service.delete_record(
                    active_id, self.approver.user_id),
                lambda: record_service.apply_transfer(
                    active_id, self.other.user_id,
                    self.submitter.user_id),
            ]
            for action in cases:
                with self.assertRaisesRegex(
                    ValueError, settle_service.SETTLING_MESSAGE
                ):
                    action()
        finally:
            ledger_dao.set_settling(self.ledger_id, False)
        self.assertTrue(self._submit())  # 锁释放后恢复可写


if __name__ == "__main__":
    unittest.main()
