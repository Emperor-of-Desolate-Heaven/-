"""dao 层：数据访问组件。

对应组件图的数据访问层，每张表一个 DAO 模块，统一通过 db.get_connection
连接 MySQL；业务层不直接写 SQL。
"""

__all__ = [
    "budget_dao",
    "grant_dao",
    "ledger_dao",
    "log_dao",
    "membership_dao",
    "record_dao",
    "settlement_dao",
    "split_dao",
    "template_dao",
    "user_dao",
]
