"""枚举定义：对应 UML 类图中的三个枚举。

- Role：账本成员角色（REQ-001）
- RecordStatus：收支记录状态（REQ-007）
- LogOpType：操作日志类型（REQ-015）
- Direction：收支方向（REQ-010 统计需要区分收入与支出）
- MembershipStatus：成员关系状态（REQ-003 加入申请流程需要，实现补充设计）
"""

from enum import Enum


class Role(Enum):
    """账本成员角色。

    需求约定：默认创建者即超级管理员，一个账本只能有一个超级管理员，
    超级管理员可转让身份（REQ-001）。
    """

    CREATOR = "创建者"
    SUPER_ADMIN = "超级管理员"
    ADMIN = "管理员"
    MEMBER = "普通用户"

    @property
    def level(self) -> int:
        """角色权限等级，数值越大权限越高。"""
        return _ROLE_LEVELS[self]


class RecordStatus(Enum):
    """收支记录状态（类图 RecordStatus，REQ-007 四状态状态机）。"""

    PENDING = "待审核"
    ACTIVE = "已生效"
    REJECTED = "已驳回"
    DELETED = "已删除"


class LogOpType(Enum):
    """操作日志类型（类图 LogOpType，REQ-015）。"""

    JOIN = "加入"
    DELETE = "删除"
    MODIFY = "修改"
    AUDIT_FAIL = "审核失败"


class MembershipStatus(Enum):
    """成员关系状态（REQ-003 加入申请）。

    待审核 = 成员已发起加入申请、等待超管审批；
    已生效 = 正式成员（申请通过或由超管直接拉入）。
    """

    PENDING = "待审核"
    ACTIVE = "已生效"


class Direction(Enum):
    """收支方向。

    金额本身恒为正数（REQ-017 拒绝负数），收入与支出由此字段区分，
    统计时分别汇总为总收入和总支出（REQ-010）。
    """

    INCOME = "收入"
    EXPENSE = "支出"


# 角色等级：创建者与超级管理员权限相同（需求约定创建者默认为超级管理员）
_ROLE_LEVELS = {
    Role.CREATOR: 3,
    Role.SUPER_ADMIN: 3,
    Role.ADMIN: 2,
    Role.MEMBER: 1,
}
