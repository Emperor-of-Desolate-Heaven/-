# dao 层 — 数据访问

对应组件图的"数据访问组件"。每张数据库表一个 DAO 模块，只负责 SQL 与
"查询结果行 ↔ 实体对象"的转换，不含业务判断（业务判断在 service 层）。

## 文件清单

| 文件 | 对应数据表 | 主要方法 |
|---|---|---|
| `db.py` | — | 连接管理 `get_connection()`：正常自动提交、异常回滚、最后关闭 |
| `user_dao.py` | user | 新增用户、按用户名/ID 查询 |
| `template_dao.py` | scene_template | 查全部模板、按 ID/类型查询 |
| `ledger_dao.py` | ledger | 创建账本、按 ID 查、按用户查其全部账本 |
| `membership_dao.py` | membership | 成员增删、改角色/可见性、按角色计数 |
| `budget_dao.py` | budget | upsert 预算（一账本至多一份）、按账本查 |
| `record_dao.py` | ledger_record | 增、按状态查、改状态/金额、查重、组合查询、按方向汇总 |
| `split_dao.py` | split_item | 批量写分摊、按记录查、删除 |
| `log_dao.py` | operation_log | 写日志、按账本查（倒序） |
| `grant_dao.py` | log_access_grant | 新增授权、查有效授权、标记已用 |
| `settlement_dao.py` | settlement | 保存结算、历史列表、最近一次 |

## 关键约定

1. **参数化 SQL**：全部使用 `%s` 占位符传参，杜绝字符串拼接注入。
2. **事务边界**：`get_connection()` 是上下文管理器，块内多条 SQL 同属一个事务，
   正常结束统一 commit，抛异常统一 rollback。
3. **行转换成实体**：每个 DAO 内的 `_row_to_xxx()` 负责把字典行转换为 model 实体，
   枚举字段在这里从字符串还原为枚举。
4. **查重规则**（`record_dao.exists_duplicate`）：除金额外其他三项
   （原因、时间、凭证）相同即疑似重复（REQ-014）；已删除记录不参与查重。
5. **统计口径**（`record_dao.sum_by_direction`）：只汇总"已生效"记录，
   待审核/已驳回/已删除不计入（与状态图"审核通过→统计更新"一致）。
6. **精度**：金额全程 Decimal；分摊比例在库中是 FLOAT，读出时经
   `Decimal(str(x))` 转换，避免二进制浮点误差。

## 本机配置

数据库密码从 `config_local.py`（git 已忽略）或环境变量读取，见
`config_local.example.py` 模板。公开仓库中不含任何密码。
