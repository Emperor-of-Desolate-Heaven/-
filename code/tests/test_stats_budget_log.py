"""统计查询（REQ-009/REQ-010/REQ-022）、预算红绿灯（REQ-019）与
日志访问授权（REQ-015）测试。

运行（在 code 目录下）：py -3.13 -m unittest tests.test_stats_budget_log -v
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from dao import grant_dao, membership_dao
from model.enums import Direction, GrantStatus, LogOpType, Role
from service import (audit_service, budget_service, log_service,
                     member_service, stats_service)
from tests.support import DbTestCase


class StatsQueryTest(DbTestCase):
    """REQ-009 组合查询 + REQ-010 主页统计 + REQ-022 可见性过滤。"""

    def setUp(self):
        self.creator = self.make_user("owner")
        self.member_a = self.make_user("a")
        self.member_b = self.make_user("b")
        self.ledger_id, self.template = self.make_ledger(self.creator)
        for user in (self.member_a, self.member_b):
            member_service.pull_in(self.ledger_id, user.username,
                                   self.creator.user_id)

    def _active(self, submitter=None, **kwargs):
        record_id = self.submit(self.ledger_id, submitter or self.creator,
                                self.template, **kwargs)
        audit_service.approve(record_id, self.creator.user_id)
        return record_id

    def _ids(self, viewer_id, **kwargs):
        records = stats_service.query_records(
            self.ledger_id, viewer_id, **kwargs
        )
        return {record.record_id for record in records}

    def test_summary_counts_only_active(self):
        """主页统计只计入已生效记录（REQ-010/REQ-017）。"""
        self._active(amount="100", direction=Direction.EXPENSE)
        self._active(amount="30", direction=Direction.INCOME)
        self.submit(self.ledger_id, self.creator, self.template,
                    amount="999")
        summary = stats_service.get_summary(
            self.ledger_id, self.creator.user_id
        )
        self.assertEqual(summary.total_expense, Decimal("100.00"))
        self.assertEqual(summary.total_income, Decimal("30.00"))
        self.assertEqual(summary.net, Decimal("-70.00"))
        self.assertIsNotNone(summary.effective_time)

    def test_combined_query_conditions(self):
        """类别 / 上传人 / 时间区间 / 金额区间及其组合（REQ-009）。"""
        base = datetime.now().replace(microsecond=0)
        categories = self.template.default_categories
        first = self._active(category=categories[0], amount="100",
                             record_time=base - timedelta(days=2))
        second = self._active(category=categories[1], amount="50",
                              record_time=base - timedelta(days=1))
        third = self._active(category=categories[0], amount="300",
                             record_time=base)
        self.assertEqual(self._ids(self.creator.user_id,
                                   category=categories[0]),
                         {first, third})
        self.assertEqual(self._ids(self.creator.user_id,
                                   submitter_id=self.creator.user_id),
                         {first, second, third})
        self.assertEqual(self._ids(self.creator.user_id,
                                   amount_min=Decimal("100")),
                         {first, third})
        self.assertEqual(self._ids(self.creator.user_id,
                                   amount_max=Decimal("100")),
                         {first, second})
        midpoint = base - timedelta(hours=36)
        self.assertEqual(self._ids(self.creator.user_id,
                                   time_from=midpoint), {second, third})
        self.assertEqual(self._ids(self.creator.user_id,
                                   time_to=midpoint), {first})
        self.assertEqual(self._ids(self.creator.user_id,
                                   category=categories[0],
                                   amount_min=Decimal("200")), {third})

    def test_rental_visibility_filter(self):
        """合租可见性：普通成员只看到自己与可见成员的记录（REQ-022）。"""
        rental_id, rental_template = self.make_ledger(self.creator, "合租")
        for user in (self.member_a, self.member_b):
            member_service.pull_in(rental_id, user.username,
                                   self.creator.user_id)
        record_a = self.submit(rental_id, self.member_a, rental_template)
        record_b = self.submit(rental_id, self.member_b, rental_template)
        for record_id in (record_a, record_b):
            audit_service.approve(record_id, self.creator.user_id)
        membership_a = membership_dao.get(rental_id, self.member_a.user_id)
        member_service.set_visibility(membership_a.membership_id, False,
                                      self.member_a.user_id)

        def ids_of(viewer_id):
            return {
                record.record_id
                for record in stats_service.query_records(
                    rental_id, viewer_id
                )
            }

        self.assertEqual(ids_of(self.member_b.user_id), {record_b})
        self.assertEqual(ids_of(self.member_a.user_id),
                         {record_a, record_b})  # B 可见
        self.assertEqual(ids_of(self.creator.user_id),
                         {record_a, record_b})  # 管理员看全部

    def test_query_rejects_non_member(self):
        """非成员不能查询账本记录。"""
        outsider = self.make_user("out")
        with self.assertRaisesRegex(PermissionError, "你不是该账本的成员"):
            stats_service.query_records(self.ledger_id, outsider.user_id)


class BudgetTest(DbTestCase):
    """REQ-019 预算设置与红绿灯。"""

    def setUp(self):
        self.creator = self.make_user("owner")
        self.member = self.make_user("member")
        self.ledger_id, self.template = self.make_ledger(self.creator)
        member_service.pull_in(self.ledger_id, self.member.username,
                               self.creator.user_id)

    def _active_expense(self, amount):
        record_id = self.submit(self.ledger_id, self.creator,
                                self.template, amount=amount)
        audit_service.approve(record_id, self.creator.user_id)

    def test_traffic_light_progression(self):
        """支出增长时红绿灯 绿 → 黄 → 红。"""
        budget_service.set_budget(self.ledger_id, self.creator.user_id,
                                  "1000")
        self.assertEqual(
            budget_service.get_traffic_light(self.ledger_id,
                                             self.creator.user_id), "绿"
        )
        self._active_expense("500")
        self.assertEqual(
            budget_service.get_traffic_light(self.ledger_id,
                                             self.creator.user_id), "绿"
        )
        self._active_expense("300")  # 累计 800 = 80%
        self.assertEqual(
            budget_service.get_traffic_light(self.ledger_id,
                                             self.creator.user_id), "黄"
        )
        self._active_expense("250")  # 累计 1050 > 100%
        self.assertEqual(
            budget_service.get_traffic_light(self.ledger_id,
                                             self.creator.user_id), "红"
        )

    def test_unset_budget_returns_none(self):
        """未设置预算时报警器不启用。"""
        self.assertIsNone(budget_service.get_budget(
            self.ledger_id, self.creator.user_id))
        self.assertIsNone(budget_service.get_traffic_light(
            self.ledger_id, self.creator.user_id))

    def test_member_can_view_budget(self):
        """预算与红绿灯所有成员可见。"""
        budget_service.set_budget(self.ledger_id, self.creator.user_id,
                                  "500")
        budget = budget_service.get_budget(self.ledger_id,
                                           self.member.user_id)
        self.assertEqual(budget.amount, Decimal("500.00"))

    def test_only_super_admin_can_set(self):
        """仅超级管理员可设置预算。"""
        with self.assertRaisesRegex(PermissionError, "仅超级管理员可设置预算"):
            budget_service.set_budget(self.ledger_id, self.member.user_id,
                                      "500")

    def test_invalid_budget_rejected(self):
        """预算金额必须为正数。"""
        for amount, message in [("abc", "预算金额必须是数字"),
                                ("0", "预算金额必须大于 0"),
                                ("-1", "预算金额必须大于 0")]:
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValueError, message):
                    budget_service.set_budget(
                        self.ledger_id, self.creator.user_id, amount
                    )


class LogAccessTest(DbTestCase):
    """REQ-015 日志查看与访问授权：申请 → 审批 → 一次有效 → 冷却期。"""

    def setUp(self):
        self.creator = self.make_user("owner")   # 超管
        self.admin = self.make_user("admin")
        self.member = self.make_user("member")
        self.ledger_id, self.template = self.make_ledger(self.creator)
        for user in (self.admin, self.member):
            member_service.pull_in(self.ledger_id, user.username,
                                   self.creator.user_id)
        admin_membership = membership_dao.get(
            self.ledger_id, self.admin.user_id
        )
        member_service.set_role(admin_membership.membership_id, Role.ADMIN,
                                self.creator.user_id)

    def test_member_denied_without_grant(self):
        """普通成员无授权不能查看日志。"""
        with self.assertRaisesRegex(PermissionError, "无有效授权"):
            log_service.view_logs(self.ledger_id, self.member.user_id)

    def test_admin_view_records_and_super_only(self):
        """管理员查看日志直接可看且留痕；查看记录仅超管可查。"""
        log_service.view_logs(self.ledger_id, self.admin.user_id)
        records = log_service.list_view_records(
            self.ledger_id, self.creator.user_id
        )
        self.assertTrue(records)
        self.assertTrue(all(record.op_type is LogOpType.VIEW
                            for record in records))
        with self.assertRaisesRegex(PermissionError, "仅超级管理员"):
            log_service.list_view_records(self.ledger_id,
                                          self.admin.user_id)

    def test_grant_lifecycle_one_time_and_cooldown(self):
        """申请 → 审批 → 使用一次 → 再次查看被拒 → 一天内不能重新申请。"""
        grant_id = log_service.request_view(
            self.ledger_id, self.member.user_id, self.admin.user_id
        )
        grant = grant_dao.get_by_id(grant_id)
        self.assertIs(grant.status, GrantStatus.PENDING)
        with self.assertRaisesRegex(PermissionError,
                                    "只能审批指派给自己的申请"):
            log_service.approve_request(grant_id, self.creator.user_id)
        log_service.approve_request(grant_id, self.admin.user_id)
        self.assertTrue(grant_dao.get_by_id(grant_id).is_valid)

        log_service.view_logs(self.ledger_id, self.member.user_id)
        self.assertTrue(grant_dao.get_by_id(grant_id).used)
        with self.assertRaisesRegex(PermissionError, "无有效授权"):
            log_service.view_logs(self.ledger_id, self.member.user_id)
        with self.assertRaisesRegex(ValueError, "距上次申请不足一天"):
            log_service.request_view(
                self.ledger_id, self.member.user_id, self.admin.user_id
            )

    def test_request_validation(self):
        """申请对象必须是管理员；不能重复申请。"""
        with self.assertRaisesRegex(ValueError, "申请对象必须是账本管理员"):
            log_service.request_view(
                self.ledger_id, self.member.user_id, self.member.user_id
            )
        grant_id = log_service.request_view(
            self.ledger_id, self.member.user_id, self.admin.user_id
        )
        with self.assertRaisesRegex(ValueError, "已有待审批的日志查看申请"):
            log_service.request_view(
                self.ledger_id, self.member.user_id, self.admin.user_id
            )
        log_service.approve_request(grant_id, self.admin.user_id)
        with self.assertRaisesRegex(ValueError, "已有有效授权"):
            log_service.request_view(
                self.ledger_id, self.member.user_id, self.admin.user_id
            )

    def test_rejected_request_grants_nothing(self):
        """被驳回的申请不能用于查看日志。"""
        grant_id = log_service.request_view(
            self.ledger_id, self.member.user_id, self.admin.user_id
        )
        log_service.reject_request(grant_id, self.admin.user_id)
        self.assertIs(grant_dao.get_by_id(grant_id).status,
                      GrantStatus.REJECTED)
        with self.assertRaisesRegex(PermissionError, "无有效授权"):
            log_service.view_logs(self.ledger_id, self.member.user_id)

    def test_grant_list_super_only_and_used_flag(self):
        """超管可查看全部授权记录，普通管理员不可。"""
        grant_id = log_service.request_view(
            self.ledger_id, self.member.user_id, self.admin.user_id
        )
        log_service.approve_request(grant_id, self.admin.user_id)
        log_service.view_logs(self.ledger_id, self.member.user_id)
        grants = log_service.list_grants(self.ledger_id,
                                         self.creator.user_id)
        self.assertTrue(grants)
        used = {grant.grant_id: grant.used for grant in grants}
        self.assertTrue(used[grant_id])
        with self.assertRaisesRegex(PermissionError, "仅超级管理员"):
            log_service.list_grants(self.ledger_id, self.admin.user_id)

    def test_applications_visible_only_to_assigned_admin(self):
        """待审批申请只出现在被指派管理员的列表中。"""
        log_service.request_view(self.ledger_id, self.member.user_id,
                                 self.admin.user_id)
        assigned = log_service.list_applications(
            self.ledger_id, self.admin.user_id
        )
        others = log_service.list_applications(
            self.ledger_id, self.creator.user_id
        )
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].membership_id,
                         membership_dao.get(self.ledger_id,
                                            self.member.user_id)
                         .membership_id)
        self.assertEqual(others, [])

    def test_non_member_cannot_view_logs(self):
        """非成员不能查看账本日志。"""
        outsider = self.make_user("out")
        with self.assertRaisesRegex(PermissionError, "你不是该账本的成员"):
            log_service.view_logs(self.ledger_id, outsider.user_id)


if __name__ == "__main__":
    unittest.main()
