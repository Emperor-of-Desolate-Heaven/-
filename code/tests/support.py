"""测试公共支撑：测试数据构造与统一清理。

所有测试数据使用固定用户名前缀（默认 t_lab3_），测试结束（包括
失败/异常）后按前缀统一删除，不会影响本机已有数据。
"""

import unittest
from datetime import datetime

from dao import db, template_dao
from model.enums import Direction
from service import auth_service, ledger_service, record_service

TEST_PREFIX = "t_lab3_"
DEFAULT_PASSWORD = "pw123456"

_COUNTER = 0


def unique_name(label: str, prefix: str = TEST_PREFIX) -> str:
    """生成带固定前缀的唯一名称（配合 cleanup_test_data 统一清理）。"""
    global _COUNTER  # pylint: disable=global-statement
    _COUNTER += 1
    stamp = datetime.now().strftime("%H%M%S")
    return f"{prefix}{label}_{stamp}_{_COUNTER}"


def cleanup_test_data(prefix: str = TEST_PREFIX) -> None:
    """删除指定前缀测试用户创建的账本及其全部关联数据，再删除用户。

    账本删除会级联清空成员、记录、分摊、日志、授权、预算与结算；
    随后再删除可能残留在其他账本中的成员关系和用户行。
    """
    like = prefix + "%"
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM user WHERE username LIKE %s",
                        (like,))
            user_ids = [row["user_id"] for row in cur.fetchall()]
            if not user_ids:
                return
            placeholders = ",".join(["%s"] * len(user_ids))
            cur.execute(
                "DELETE FROM ledger WHERE ledger_id IN "
                "(SELECT DISTINCT ledger_id FROM membership "
                f"WHERE user_id IN ({placeholders}))",
                tuple(user_ids),
            )
            cur.execute(
                f"DELETE FROM membership WHERE user_id IN ({placeholders})",
                tuple(user_ids),
            )
            cur.execute(
                f"DELETE FROM user WHERE user_id IN ({placeholders})",
                tuple(user_ids),
            )


class DbTestCase(unittest.TestCase):
    """数据库集成测试基类：类级清理测试数据，并提供构造数据的辅助方法。

    每个测试类开始前清理一次历史残留，结束后清理本类产生的数据。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cleanup_test_data()

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_test_data()

    @staticmethod
    def make_user(label: str = "u"):
        """注册一个测试用户并返回 User 实体。"""
        return auth_service.register(unique_name(label), DEFAULT_PASSWORD)

    @staticmethod
    def make_ledger(creator, template_type: str = "旅行", name=None):
        """以 creator 身份创建指定模板的账本，返回 (ledger_id, 模板)。"""
        template = template_dao.get_by_type(template_type)
        ledger_id = ledger_service.create_ledger(
            name or unique_name("账本"), template.template_id,
            creator.user_id,
        )
        return ledger_id, template

    @staticmethod
    def submit(  # pylint: disable=too-many-arguments
        ledger_id: int,
        submitter,
        template,
        *,
        amount="100",
        reason=None,
        category=None,
        direction=Direction.EXPENSE,
        record_time=None,
        receipt="",
        split_items=None,
    ) -> int:
        """提交一条测试记录，返回记录 ID（原因默认唯一，避免触发查重）。"""
        return record_service.submit_record(
            ledger_id,
            submitter.user_id,
            category or template.default_categories[0],
            reason or unique_name("原因"),
            amount,
            direction,
            record_time or datetime.now(),
            receipt,
            split_items,
        )
