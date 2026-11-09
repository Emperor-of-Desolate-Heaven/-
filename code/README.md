# 多人共享记账系统（实验三实现）

根据实验二的 UML 设计（类图 / 状态图 / 时序图 / 组件图）实现的命令行记账系统。
Python 3.13 + MySQL 8.0，分三层实现，对应组件图的分层架构。

## 目录结构

```
code/
├── main.py            # 程序入口（命令行主菜单）
├── schema.sql         # 建库建表脚本（10 张表，对应类图 10 个实体）
├── config_local.example.py  # 本机数据库密码配置模板
├── model/             # 实体与枚举层：对应类图 10 个实体 + 3 个枚举【已完成】
├── dao/               # 数据访问层：每张表一个 DAO，统一走 MySQL【已完成】
├── service/           # 业务逻辑层：9 个业务模块（对应组件图 SVC_*）【已完成】
├── presentation/      # 表现层：命令行界面（对应组件图 UI_*）【待实现】
└── tests/             # 单元测试与模拟用户测试【待实现】
```

## 运行环境

- Python 3.13（本机命令为 `py -3.13`）
- MySQL 8.0，已执行 `schema.sql` 建库（数据库名 `ledger_db`）
- 依赖：`py -3.13 -m pip install pymysql pylint`

## 配置

复制 `config_local.example.py` 为 `config_local.py`，填入本机 MySQL 密码。
`config_local.py` 已被 git 忽略，不会提交到公开仓库。
也可改用环境变量：`LEDGER_DB_HOST` / `LEDGER_DB_PORT` / `LEDGER_DB_USER` /
`LEDGER_DB_PASSWORD` / `LEDGER_DB_NAME`。

## 运行

```bash
cd code
py -3.13 main.py
```

## 分层约定

- **model**：纯数据类 + 纯计算逻辑（红绿灯、状态机转换、分摊计算），不访问数据库
- **dao**：只写 SQL 与行↔实体的转换，不做业务判断
- **service**：业务规则、权限校验、状态流转（对应需求 REQ-001 ~ REQ-026）
- **presentation**：菜单与输入输出，不直接访问 dao
