"""service 层：业务逻辑。

对应组件图业务逻辑层的 9 个模块（SVC_*）。业务规则、权限校验、
状态流转都在本层；本层只调用 dao，不直接写 SQL。
"""

__all__ = ["auth_service", "ledger_service", "member_service"]
