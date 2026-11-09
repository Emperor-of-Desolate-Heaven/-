# presentation 层 — 命令行界面

对应组件图表现层的 8 个界面组件（UI_*），每个界面一个模块；
[main.py](../main.py) 为程序入口。本层只调用 service，不直接访问 dao，
组件图"依赖方向自上而下"的约定在本层严格保持。

## 文件清单

| 文件 | 对应组件图组件 | 功能 |
|---|---|---|
| `console.py` | —（公共工具） | 会话 Session、输入解析、菜单循环、业务异常转提示 |
| `login_view.py` | UI_Login | 注册、登录（REQ-020） |
| `ledger_view.py` | UI_NewLedger | 我的账本列表（含待审批申请）、创建账本（选模板）、申请加入（REQ-002/003/026） |
| `home_view.py` | UI_Home | 账本主页：统计/红绿灯/生效时间、提交记录（含分摊输入）、记录操作、设置预算（REQ-004~008/010/019） |
| `query_view.py` | UI_Query | 记录列表与四条件组合查询、记录详情（分摊明细）（REQ-009） |
| `audit_view.py` | UI_Audit | 待审核列表、审核通过/驳回（REQ-006/007） |
| `member_view.py` | UI_Member | 成员列表、加入审批、拉人、改角色、超管转让、可见性、退出/踢人（REQ-001/003/022） |
| `settle_view.py` | UI_Settle | 执行结算（选结算日期）、结算历史（REQ-011/012） |
| `log_view.py` | UI_Log | 查看日志、普通成员申请、管理员审批、超管查看查看记录/授权记录（REQ-015） |

## 约定

1. **会话传递**：登录成功后生成 `Session(user_id, username)`，
   逐层传给各界面；退出登录后丢弃。
2. **导航**：`login_view → ledger_view（我的账本）→ home_view（账本主页）`
   为主导航；主页菜单路由到查询/审核/成员/结算/日志界面，
   各界面"0 返回"逐级回退。
3. **异常统一处理**：所有 service 调用都经 `console.run()` 包装，
   业务异常（ValueError / PermissionError）转成一行
   "操作失败：原因"，不会中断界面循环。
4. **按角色显示菜单**：审核管理、设置预算等条目只对相应角色显示
   （通过 `member_service.get_membership` 判断），越权操作仍由
   service 层兜底拒绝。
5. **只做输入输出**：界面负责提示、收集输入、展示结果；
   所有校验与状态流转都在 service 层完成。

## 设计补充说明（报告可引用）

- 组件图没有"我的账本列表"独立组件，实现中把账本选择并入
  UI_NewLedger（账本页），并在服务层补充了 `list_ledgers_with_membership`
  （展示"申请待审批"状态）等只读查询接口。
- 组件图 UI_Home 依赖 SVC_Record/SVC_Stats/SVC_Budget，实现中
  "记录操作（重新提交/改金额/删除/转让）"也放在主页，与组件图一致。
- 首次结算的周期起点对齐到分钟：记录时间输入只精确到分钟，
  账本生效时间带秒，不处理会把账本创建同一分钟内的记录排除在
  结算之外。
