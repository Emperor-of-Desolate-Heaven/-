# model 层 — 实体与枚举

对应实验二类图的 10 个实体类与 3 个枚举。本层只承载数据与**纯计算逻辑**，
不访问数据库；需要落库的操作（登录、审核等）在 service 层实现。

## 文件清单

| 文件 | 对应类图元素 | 说明 |
|---|---|---|
| `enums.py` | Role / RecordStatus / LogOpType | 三个枚举；另含 Direction（收支方向，REQ-010 统计需要） |
| `user.py` | 用户 | 用户 ID、用户名、密码哈希 |
| `scene_template.py` | 场景模板 | 旅行/合租/家庭三套模板的默认类别、结算方式、预算口径 |
| `ledger.py` | 账本 | 账本名称、所用模板、生效时间 |
| `membership.py` | 成员关系 | 用户在账本中的角色与可见性开关 |
| `budget.py` | 预算 | 预算金额 + 红绿灯计算（REQ-019） |
| `ledger_record.py` | 收支记录 | 记录字段 + 状态机转换表（REQ-007） |
| `split_item.py` | 分摊明细 | 参与人比例 + 按比例算应分摊金额（REQ-013） |
| `operation_log.py` | 操作日志 | 加入/删除/修改/审核失败四类操作留痕（REQ-015） |
| `log_access_grant.py` | 日志访问授权 | 申请—审批—一次有效（REQ-015） |
| `settlement.py` | 结算 | 自动结算结果（REQ-011） |

## 设计要点

1. **dataclass**：实体用标准库 `@dataclass`，字段带类型标注，符合 PEP 8 风格。
2. **金额用 Decimal**：与 MySQL DECIMAL(12,2) 对应，避免浮点误差。
3. **纯计算留在 model**：
   - `Budget.traffic_light()`：<80% 绿、80%~100% 黄、>100% 红（REQ-019）
   - `LedgerRecord.can_transition_to()`：四状态状态机的合法转换（REQ-007）
   - `SplitItem.share_amount()`：按比例分摊
   - `Membership.is_admin / is_super_admin`：角色权限判断
4. **状态机集中定义**：`ledger_record.py` 顶部的 `ALLOWED_TRANSITIONS`
   是唯一的状态转换依据，service 层与单元测试都引用它，避免规则分散。

## 与类图的差异

- 新增 `Direction` 枚举（收入/支出）：需求 REQ-017 规定金额恒为正数，
  但统计要区分总收入与总支出（REQ-010），因此增加方向字段。
