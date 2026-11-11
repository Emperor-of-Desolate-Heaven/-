"""model 层纯逻辑单元测试（不连接数据库）。

覆盖：REQ-007 状态机全路径、REQ-019 红绿灯阈值、REQ-013 分摊计算、
REQ-001 角色权限、REQ-015 授权有效性、REQ-026 模板结算能力。
"""

import unittest
from decimal import Decimal

from model.budget import Budget
from model.enums import GrantStatus, RecordStatus, Role
from model.ledger_record import ALLOWED_TRANSITIONS, LedgerRecord
from model.log_access_grant import LogAccessGrant
from model.membership import Membership
from model.scene_template import SceneTemplate
from model.split_item import SplitItem


class RecordStateMachineTest(unittest.TestCase):
    """REQ-007 四状态状态机：全部 16 种转换逐一验证。"""

    def test_full_transition_matrix(self):
        """4×4 状态矩阵与 ALLOWED_TRANSITIONS 完全一致。"""
        for source in RecordStatus:
            for target in RecordStatus:
                with self.subTest(source=source, target=target):
                    record = LedgerRecord(status=source)
                    expected = target in ALLOWED_TRANSITIONS[source]
                    self.assertEqual(
                        record.can_transition_to(target), expected
                    )

    def test_forbidden_paths(self):
        """需求明确禁止的三类转换。"""
        # 已驳回 → 已生效：必须重新提交并再次审核
        rejected = LedgerRecord(status=RecordStatus.REJECTED)
        self.assertFalse(rejected.can_transition_to(RecordStatus.ACTIVE))
        # 已删除 → 任何状态：不可恢复
        deleted = LedgerRecord(status=RecordStatus.DELETED)
        for target in RecordStatus:
            with self.subTest(target=target):
                self.assertFalse(deleted.can_transition_to(target))
        # 待审核 → 已删除：待审核期间记录被锁定
        pending = LedgerRecord(status=RecordStatus.PENDING)
        self.assertFalse(pending.can_transition_to(RecordStatus.DELETED))

    def test_is_locked_only_pending(self):
        """仅待审核记录处于锁定状态。"""
        self.assertTrue(LedgerRecord(status=RecordStatus.PENDING).is_locked)
        for status in (RecordStatus.ACTIVE, RecordStatus.REJECTED,
                       RecordStatus.DELETED):
            with self.subTest(status=status):
                self.assertFalse(LedgerRecord(status=status).is_locked)


class BudgetTrafficLightTest(unittest.TestCase):
    """REQ-019 红绿灯阈值：<80% 绿，80%~100% 黄，>100% 红。"""

    def test_threshold_boundaries(self):
        """覆盖阈值两侧的边界值。"""
        budget = Budget(amount=Decimal("1000.00"))
        cases = [
            ("0", "绿"),
            ("799.99", "绿"),
            ("800.00", "黄"),      # 恰好 80% 进入黄色
            ("999.99", "黄"),
            ("1000.00", "黄"),     # 恰好 100% 仍是黄色
            ("1000.01", "红"),     # 超过 100% 变红
        ]
        for expense, expected in cases:
            with self.subTest(expense=expense):
                self.assertEqual(
                    budget.traffic_light(Decimal(expense)), expected
                )

    def test_nonpositive_budget_always_red(self):
        """预算金额非正时视为已超标（防御性口径）。"""
        for amount in ("0", "-1"):
            with self.subTest(amount=amount):
                budget = Budget(amount=Decimal(amount))
                self.assertEqual(
                    budget.traffic_light(Decimal("1")), "红"
                )

    def test_usage_ratio(self):
        """使用比例 = 总支出 / 预算金额。"""
        budget = Budget(amount=Decimal("1000"))
        self.assertEqual(
            budget.usage_ratio(Decimal("250")), Decimal("0.25")
        )


class SplitItemTest(unittest.TestCase):
    """REQ-013 分摊金额计算：按比例四舍五入保留两位小数。"""

    def test_share_amount_rounded(self):
        """分摊金额 = 总额 × 比例，保留两位小数。"""
        cases = [
            ("100", "0.6", "60.00"),
            ("100", "0.333", "33.30"),
            ("99.99", "0.3333", "33.33"),
            ("0.03", "0.5", "0.02"),   # 0.015 四舍五入
        ]
        for total, ratio, expected in cases:
            with self.subTest(total=total, ratio=ratio):
                item = SplitItem(ratio=Decimal(ratio))
                self.assertEqual(
                    item.share_amount(Decimal(total)), Decimal(expected)
                )

    def test_zero_ratio(self):
        """比例为 0 时不分摊任何金额。"""
        self.assertEqual(
            SplitItem(ratio=Decimal("0")).share_amount(Decimal("100")),
            Decimal("0.00"),
        )


class RolePermissionTest(unittest.TestCase):
    """REQ-001 角色权限：创建者与超管同级。"""

    def test_role_levels_ordered(self):
        """权限等级：普通用户 < 管理员 < 超管 = 创建者。"""
        self.assertLess(Role.MEMBER.level, Role.ADMIN.level)
        self.assertLess(Role.ADMIN.level, Role.SUPER_ADMIN.level)
        self.assertEqual(Role.CREATOR.level, Role.SUPER_ADMIN.level)

    def test_membership_flags(self):
        """is_admin / is_super_admin 对四种角色的判定。"""
        cases = [
            (Role.CREATOR, True, True),
            (Role.SUPER_ADMIN, True, True),
            (Role.ADMIN, True, False),
            (Role.MEMBER, False, False),
        ]
        for role, expect_admin, expect_super in cases:
            with self.subTest(role=role):
                member = Membership(role=role)
                self.assertEqual(member.is_admin, expect_admin)
                self.assertEqual(member.is_super_admin, expect_super)


class TemplateAndGrantTest(unittest.TestCase):
    """REQ-026 模板结算能力 + REQ-015 授权一次有效。"""

    def test_template_settlement_support(self):
        """旅行/合租结算，家庭不结算。"""
        self.assertTrue(
            SceneTemplate(settle_method="AA均摊").supports_settlement
        )
        self.assertTrue(
            SceneTemplate(settle_method="按分摊比例").supports_settlement
        )
        self.assertFalse(
            SceneTemplate(settle_method="不结算").supports_settlement
        )

    def test_grant_valid_only_approved_and_unused(self):
        """授权有效 = 已批准且未使用。"""
        cases = [
            (GrantStatus.PENDING, False, False),
            (GrantStatus.APPROVED, False, True),
            (GrantStatus.APPROVED, True, False),
            (GrantStatus.REJECTED, False, False),
        ]
        for status, used, expected in cases:
            with self.subTest(status=status, used=used):
                grant = LogAccessGrant(status=status, used=used)
                self.assertEqual(grant.is_valid, expected)


if __name__ == "__main__":
    unittest.main()
