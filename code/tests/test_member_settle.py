"""成员管理（REQ-001/REQ-003/REQ-022）与结算（REQ-011/REQ-012/REQ-026）测试。

运行（在 code 目录下）：py -3.13 -m unittest tests.test_member_settle -v
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from dao import ledger_dao, log_dao, membership_dao, record_dao
from model.enums import Direction, LogOpType, MembershipStatus, Role, \
    RecordStatus
from model.split_item import SplitItem
from service import audit_service, member_service, settle_service
from tests.support import DbTestCase


class MemberFlowTest(DbTestCase):
    """REQ-001/REQ-003：加入申请、拉人、角色、超管转让、可见性、退出。"""

    def setUp(self):
        self.creator = self.make_user("owner")
        self.member = self.make_user("member")
        self.ledger_id, self.template = self.make_ledger(self.creator)

    def _pull_in(self, user):
        member_service.pull_in(self.ledger_id, user.username,
                               self.creator.user_id)
        return membership_dao.get(self.ledger_id, user.user_id)

    def test_apply_and_approve_join(self):
        """申请 → 待审核 → 超管审批 → 已生效，并记录加入日志。"""
        membership_id = member_service.apply_join(
            self.ledger_id, self.member.user_id
        )
        pending = membership_dao.get_by_id(membership_id)
        self.assertIs(pending.status, MembershipStatus.PENDING)
        with self.assertRaisesRegex(PermissionError, "你不是该账本的成员"):
            self.submit(self.ledger_id, self.member, self.template)
        applications = member_service.list_applications(
            self.ledger_id, self.creator.user_id
        )
        self.assertEqual([info.username for info in applications],
                         [self.member.username])
        member_service.approve_join(membership_id, self.creator.user_id)
        self.assertIs(
            membership_dao.get_by_id(membership_id).status,
            MembershipStatus.ACTIVE,
        )
        joins = log_dao.list_by_type(self.ledger_id, LogOpType.JOIN)
        self.assertIn(self.member.user_id,
                      [log.submitter_id for log in joins])
        self.assertTrue(self.submit(self.ledger_id, self.member,
                                    self.template))

    def test_apply_twice_rejected(self):
        """重复申请加入被拒绝。"""
        member_service.apply_join(self.ledger_id, self.member.user_id)
        with self.assertRaisesRegex(ValueError, "你已申请或已加入该账本"):
            member_service.apply_join(self.ledger_id, self.member.user_id)

    def test_only_super_admin_can_approve_join(self):
        """管理员（非超管）不能审批加入申请（REQ-001）。"""
        admin_membership = self._pull_in(self.member)
        member_service.set_role(
            admin_membership.membership_id, Role.ADMIN, self.creator.user_id
        )
        applicant = self.make_user("applicant")
        membership_id = member_service.apply_join(
            self.ledger_id, applicant.user_id
        )
        with self.assertRaisesRegex(PermissionError, "仅超级管理员"):
            member_service.approve_join(membership_id, self.member.user_id)
        with self.assertRaisesRegex(PermissionError, "仅超级管理员"):
            member_service.list_applications(
                self.ledger_id, self.member.user_id
            )

    def test_pull_in_validation(self):
        """拉人：用户必须存在且尚未加入。"""
        member_service.pull_in(self.ledger_id, self.member.username,
                               self.creator.user_id)
        member = membership_dao.get(self.ledger_id, self.member.user_id)
        self.assertIs(member.status, MembershipStatus.ACTIVE)
        with self.assertRaisesRegex(ValueError, "该用户已申请或已加入该账本"):
            member_service.pull_in(self.ledger_id, self.member.username,
                                   self.creator.user_id)
        with self.assertRaisesRegex(ValueError, "用户不存在"):
            member_service.pull_in(self.ledger_id, "不存在的人",
                                   self.creator.user_id)

    def test_set_role_rules(self):
        """角色修改：不能直接设超管、不能改超管、仅超管可操作。"""
        member = self._pull_in(self.member)
        member_service.set_role(member.membership_id, Role.ADMIN,
                                self.creator.user_id)
        self.assertIs(membership_dao.get_by_id(member.membership_id).role,
                      Role.ADMIN)
        with self.assertRaisesRegex(PermissionError, "不能直接设置超管角色"):
            member_service.set_role(member.membership_id, Role.SUPER_ADMIN,
                                    self.creator.user_id)
        creator_membership = membership_dao.get(
            self.ledger_id, self.creator.user_id
        )
        with self.assertRaisesRegex(PermissionError,
                                    "超管角色只能通过身份转让变更"):
            member_service.set_role(creator_membership.membership_id,
                                    Role.MEMBER, self.creator.user_id)
        with self.assertRaisesRegex(PermissionError, "仅超级管理员"):
            member_service.set_role(member.membership_id, Role.MEMBER,
                                    self.member.user_id)

    def test_transfer_super_admin(self):
        """超管转让：新超管生效、原超管降为普通用户、始终只有一个超管。"""
        target = self._pull_in(self.member)
        member_service.transfer_super_admin(
            self.ledger_id, self.member.user_id, self.creator.user_id
        )
        self.assertIs(membership_dao.get_by_id(target.membership_id).role,
                      Role.SUPER_ADMIN)
        creator_membership = membership_dao.get(
            self.ledger_id, self.creator.user_id
        )
        self.assertIs(creator_membership.role, Role.MEMBER)
        self.assertEqual(
            membership_dao.count_by_role(self.ledger_id, Role.SUPER_ADMIN), 1
        )
        with self.assertRaisesRegex(ValueError, "该成员已是超级管理员"):
            member_service.transfer_super_admin(
                self.ledger_id, self.member.user_id, self.member.user_id
            )

    def test_visibility_rules(self):
        """可见性仅合租账本、仅本人设置（REQ-022）。"""
        rental_id, _ = self.make_ledger(self.creator, "合租")
        member_service.pull_in(rental_id, self.member.username,
                               self.creator.user_id)
        member = membership_dao.get(rental_id, self.member.user_id)
        member_service.set_visibility(member.membership_id, False,
                                      self.member.user_id)
        self.assertFalse(
            membership_dao.get_by_id(member.membership_id).visibility_on
        )
        creator_membership = membership_dao.get(
            rental_id, self.creator.user_id
        )
        with self.assertRaisesRegex(PermissionError, "可见性只能由本人设置"):
            member_service.set_visibility(creator_membership.membership_id,
                                          False, self.member.user_id)
        travel_membership = membership_dao.get(
            self.ledger_id, self.creator.user_id
        )
        with self.assertRaisesRegex(PermissionError,
                                    "该模板不支持可见性设置"):
            member_service.set_visibility(travel_membership.membership_id,
                                          False, self.creator.user_id)

    def test_exit_transfers_records_to_super_admin(self):
        """退出/踢人：待审核记录审核失败，已生效记录默认转让给超管（REQ-003）。"""
        member = self._pull_in(self.member)
        pending_id = self.submit(self.ledger_id, self.member, self.template)
        active_id = self.submit(self.ledger_id, self.member, self.template)
        audit_service.approve(active_id, self.creator.user_id)
        member_service.remove_member(member.membership_id,
                                     self.creator.user_id)
        self.assertIsNone(membership_dao.get(self.ledger_id,
                                             self.member.user_id))
        self.assertIs(record_dao.get_by_id(pending_id).status,
                      RecordStatus.REJECTED)
        transferred = record_dao.get_by_id(active_id)
        self.assertEqual(transferred.submitter_id, self.creator.user_id)
        audit_logs = log_dao.list_by_type(
            self.ledger_id, LogOpType.AUDIT_FAIL
        )
        self.assertTrue(audit_logs)
        delete_logs = log_dao.list_by_type(self.ledger_id, LogOpType.DELETE)
        self.assertIn(self.member.user_id,
                      [log.submitter_id for log in delete_logs])

    def test_exit_cancel_records(self):
        """退出时可选择注销全部记录。"""
        member = self._pull_in(self.member)
        record_id = self.submit(self.ledger_id, self.member, self.template)
        audit_service.approve(record_id, self.creator.user_id)
        member_service.remove_member(member.membership_id,
                                     self.creator.user_id,
                                     cancel_records=True)
        self.assertIs(record_dao.get_by_id(record_id).status,
                      RecordStatus.DELETED)

    def test_exit_permissions(self):
        """超管须先转让身份才能退出；普通成员可自行退出。"""
        creator_membership = membership_dao.get(
            self.ledger_id, self.creator.user_id
        )
        with self.assertRaisesRegex(PermissionError, "超管请先转让身份再退出"):
            member_service.remove_member(creator_membership.membership_id,
                                         self.creator.user_id)
        member = self._pull_in(self.member)
        member_service.remove_member(member.membership_id,
                                     self.member.user_id)
        self.assertIsNone(membership_dao.get(self.ledger_id,
                                             self.member.user_id))


class SettlementTest(DbTestCase):
    """REQ-011/REQ-012/REQ-026 结算规则与结算锁。"""

    def setUp(self):
        self.creator = self.make_user("owner")
        self.member = self.make_user("member")
        self.tomorrow = datetime.now() + timedelta(days=1)

    def _ledger(self, template_type="旅行"):
        ledger_id, template = self.make_ledger(self.creator, template_type)
        if template_type == "合租":
            member_service.pull_in(ledger_id, self.member.username,
                                   self.creator.user_id)
        return ledger_id, template

    def _active(self, ledger_id, template, submitter=None, **kwargs):
        record_id = self.submit(ledger_id, submitter or self.creator,
                                template, **kwargs)
        audit_service.approve(record_id, self.creator.user_id)
        return record_id

    def test_family_ledger_has_no_settlement(self):
        """家庭账本不结算（REQ-026）。"""
        ledger_id, _ = self._ledger("家庭")
        with self.assertRaisesRegex(ValueError, "家庭账本不结算"):
            settle_service.settle(ledger_id, self.creator.user_id,
                                  self.tomorrow)
        self.assertEqual(
            settle_service.list_settlements(ledger_id,
                                            self.creator.user_id), []
        )

    def test_travel_settlement_totals_and_lock_release(self):
        """旅行一次性结算：总支出/总收入/条数；结算后锁自动释放。"""
        ledger_id, template = self._ledger("旅行")
        self._active(ledger_id, template, amount="100",
                     direction=Direction.EXPENSE)
        self._active(ledger_id, template, amount="50",
                     direction=Direction.INCOME)
        settlement = settle_service.settle(
            ledger_id, self.creator.user_id, self.tomorrow
        )
        self.assertIn("总支出 100.00 元", settlement.result)
        self.assertIn("总收入 50.00 元", settlement.result)
        self.assertIn("记录 2 条", settlement.result)
        self.assertIn("至", settlement.period)
        self.assertFalse(ledger_dao.is_settling(ledger_id))
        self.assertEqual(
            len(settle_service.list_settlements(ledger_id,
                                                self.creator.user_id)), 1
        )

    def test_pending_and_future_records_excluded(self):
        """待审核记录、结算时间点之后的记录不参与结算（REQ-012）。"""
        ledger_id, template = self._ledger("旅行")
        self.submit(ledger_id, self.creator, template, amount="100")
        self._active(ledger_id, template, amount="30",
                     direction=Direction.INCOME)
        self._active(ledger_id, template, amount="200",
                     record_time=self.tomorrow + timedelta(hours=12))
        settlement = settle_service.settle(
            ledger_id, self.creator.user_id, self.tomorrow
        )
        self.assertIn("记录 1 条", settlement.result)
        self.assertIn("总支出 0.00 元", settlement.result)
        self.assertIn("总收入 30.00 元", settlement.result)

    def test_second_period_starts_from_last_settlement(self):
        """第二次结算的周期起点为上次结算时间点，旧记录不重复统计。"""
        ledger_id, template = self._ledger("旅行")
        self._active(ledger_id, template, amount="100")
        first = settle_service.settle(
            ledger_id, self.creator.user_id, self.tomorrow
        )
        self.assertIn("记录 1 条", first.result)
        second = settle_service.settle(
            ledger_id, self.creator.user_id,
            self.tomorrow + timedelta(days=1),
        )
        self.assertIn("记录 0 条", second.result)

    def test_shared_per_person_payable(self):
        """合租结算输出每人应付明细：按分摊比例，无分摊归提交人，
        收入不计入应付（REQ-011/REQ-013/REQ-026）。"""
        ledger_id, template = self._ledger("合租")
        owner, member = self.creator, self.member
        split_items = [
            SplitItem(user_id=owner.user_id, ratio=Decimal("0.6")),
            SplitItem(user_id=member.user_id, ratio=Decimal("0.4")),
        ]
        self._active(ledger_id, template, submitter=owner, amount="100",
                     split_items=split_items)
        self._active(ledger_id, template, submitter=member, amount="30")
        self._active(ledger_id, template, submitter=member, amount="20",
                     direction=Direction.INCOME,
                     split_items=[
                         SplitItem(user_id=owner.user_id,
                                   ratio=Decimal("0.5")),
                         SplitItem(user_id=member.user_id,
                                   ratio=Decimal("0.5")),
                     ])
        settlement = settle_service.settle(
            ledger_id, self.creator.user_id, self.tomorrow
        )
        self.assertIn("总支出 130.00 元", settlement.result)
        self.assertIn("总收入 20.00 元", settlement.result)
        self.assertIn("每人应付：", settlement.result)
        self.assertIn(f"{owner.username} 60.00 元", settlement.result)
        self.assertIn(f"{member.username} 70.00 元", settlement.result)

    def test_settle_requires_admin(self):
        """普通成员不能执行结算。"""
        ledger_id, _ = self._ledger("旅行")
        member_service.pull_in(ledger_id, self.member.username,
                               self.creator.user_id)
        with self.assertRaisesRegex(PermissionError, "仅管理员可执行结算"):
            settle_service.settle(ledger_id, self.member.user_id,
                                  self.tomorrow)

    def test_settlement_history_requires_membership(self):
        """结算历史仅成员可查看。"""
        ledger_id, template = self._ledger("旅行")
        self._active(ledger_id, template)
        settle_service.settle(ledger_id, self.creator.user_id,
                              self.tomorrow)
        outsider = self.make_user("out")
        with self.assertRaisesRegex(PermissionError, "你不是该账本的成员"):
            settle_service.list_settlements(ledger_id, outsider.user_id)


if __name__ == "__main__":
    unittest.main()
