"""presentation 层：命令行界面。

对应组件图表现层的 8 个界面组件（UI_*）。本层只调用 service，
不直接访问 dao；业务异常（ValueError / PermissionError）统一由
console.run() 捕获并转为一行"操作失败：…"提示。
"""

__all__ = ["console", "login_view", "ledger_view", "home_view",
           "query_view", "audit_view", "member_view", "settle_view",
           "log_view"]
