# 多人共享记账系统（实验三实现）

根据实验二的 UML 设计（类图 / 状态图 / 时序图 / 组件图）实现的命令行记账系统。
Python 3.13 + MySQL 8.0，分三层实现，对应组件图的分层架构。

## 目录结构

```
code/
├── main.py            # 程序入口（命令行主菜单）
├── schema.sql         # 建库建表脚本（10 张表，对应类图 10 个实体）
├── config_local.example.py  # 数据库连接配置模板（本机/远程服务器）
├── model/             # 实体与枚举层：对应类图 10 个实体 + 3 个枚举【已完成】
├── dao/               # 数据访问层：每张表一个 DAO，统一走 MySQL【已完成】
├── service/           # 业务逻辑层：9 个业务模块（对应组件图 SVC_*）【已完成】
├── presentation/      # 表现层：命令行界面（对应组件图 UI_*）【已完成】
└── tests/             # 单元测试与模拟用户测试（67 项）【已完成】
```

## 运行环境

- Python 3.13（本机命令为 `py -3.13`）
- MySQL 8.0，已执行 `schema.sql` 建库（数据库名 `ledger_db`）
- 依赖：`py -3.13 -m pip install pymysql pylint`

## 配置

连接参数按 **环境变量 > config_local.py > 默认值** 的顺序读取
（默认值：`127.0.0.1:3306` / `root` / `ledger_db`，即本机 MySQL）。

- 连接本机 MySQL：复制 `config_local.example.py` 为 `config_local.py`，
  填 `DB_PASSWORD` 即可，其余保持默认；
- 连接远程服务器（多人共享）：在 `config_local.py` 中把 `DB_HOST` 改为服务器 IP，
  `DB_USER` / `DB_PASSWORD` 填服务器分配的账号；或改用环境变量
  `LEDGER_DB_HOST` / `LEDGER_DB_PORT` / `LEDGER_DB_USER` /
  `LEDGER_DB_PASSWORD` / `LEDGER_DB_NAME`。

`config_local.py` 已被 git 忽略，不会提交到公开仓库。

## 多人共享部署（数据库放服务器）

所有用户连接同一台 MySQL 服务器，数据天然共享；
客户端只装 Python 和程序，**不需要安装 MySQL**。

**服务器端（只需配置一次）**

1. 安装并启动 MySQL 8.0；
2. 用管理员账号执行 `schema.sql` 建库建表；
3. 为客户端建一个只访问本库的账号：

   ```sql
   CREATE USER 'ledger_app'@'%' IDENTIFIED BY '换成强密码';
   GRANT ALL PRIVILEGES ON ledger_db.* TO 'ledger_app'@'%';
   FLUSH PRIVILEGES;
   ```
4. 确认 MySQL 监听外部地址（`bind_address` 为 `*` 或服务器网卡地址），
   并在防火墙放行 3306 端口。
   课程演示在局域网内使用即可，不建议直接暴露到公网。

**客户端（每个用户）**

1. 安装 Python 3.13 与依赖：`py -3.13 -m pip install pymysql`；
2. 获取 `code/` 目录，复制 `config_local.example.py` 为 `config_local.py`，
   把 `DB_HOST` 填为服务器 IP，`DB_USER` / `DB_PASSWORD` 填分配的账号；
3. 运行 `py -3.13 main.py`。

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
