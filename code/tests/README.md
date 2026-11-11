# tests —— 测试层

## 职责

验证 model 层纯逻辑、service 层业务规则与整套命令行流程是否满足实验二
需求清单（REQ-001 ~ REQ-026），包括状态机、权限、结算、可见性、
日志授权与竞争加锁等关键约束。

## 文件清单

| 文件 | 类型 | 覆盖内容 |
|---|---|---|
| test_model_logic.py | 单元测试（无数据库） | REQ-007 状态机 4×4 全矩阵、REQ-019 红绿灯边界、REQ-013 分摊取整、REQ-001 角色权限、REQ-015 授权有效性、REQ-026 模板结算能力 |
| test_record_flow.py | 集成测试（MySQL） | REQ-020 注册登录、REQ-002 建账、REQ-004 ~ REQ-008 提交/审核/驳回/重提/改金额/删除/转让、REQ-012 结算锁、REQ-014 查重、条件 UPDATE 竞争加锁 |
| test_member_settle.py | 集成测试（MySQL） | REQ-001/REQ-003 加入审批/拉人/角色/超管转让/退出、REQ-022 可见性、REQ-011/REQ-026 结算规则与结算锁 |
| test_stats_budget_log.py | 集成测试（MySQL） | REQ-009 组合查询、REQ-010 统计、REQ-022 可见性过滤、REQ-019 红绿灯、REQ-015 日志授权全生命周期 |
| support.py | 公共支撑 | 测试用户/账本/记录构造，按前缀统一清理测试数据 |
| simulate_user.py | 模拟用户测试 | 两个虚拟用户通过真实命令行界面走完整业务流程（注册 → 建账 → 提交 → 加入 → 审批 → 审核 → 预算 → 结算 → 日志授权） |

## 运行方式

在 `code/` 目录下执行（需 MySQL 已启动、`config_local.py` 配置正确）：

```bash
# 全部单元测试与集成测试（67 项）
py -3.13 -m unittest discover -s tests -t . -v

# 单个测试文件
py -3.13 -m unittest tests.test_record_flow -v

# 模拟用户端到端测试
py -3.13 tests/simulate_user.py
```

## 设计要点

1. **纯逻辑与集成分离**：`test_model_logic.py` 不访问数据库，直接验证
   实体类中的状态机、红绿灯、分摊等纯计算；其余测试走 service → dao →
   MySQL 的真实链路。
2. **测试数据隔离**：集成测试用户名统一带 `t_lab3_` 前缀（模拟用户脚本用
   `sim_lab3_`），每个测试类开始与结束时按前缀清理，不依赖数据库初始状态，
   也不会影响已有数据。
3. **结算测试的时间口径**：结算时间点由 `settle_at` 显式传入（通常取明日），
   使当天提交的记录落在统计区间内，测试结果不受执行时刻影响。
4. **模拟用户测试**采用替换 `builtins.input` 的方式驱动真实
   presentation 层菜单，等价于真人逐项输入；脚本最后核对数据库状态并清理。
