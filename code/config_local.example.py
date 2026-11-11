"""数据库连接配置模板（本机或远程服务器均可）。

使用方法：把本文件复制为同目录下的 config_local.py，按需填写。
config_local.py 已被 git 忽略，不会提交到仓库。
环境变量（LEDGER_DB_HOST 等）优先级高于本文件；未填写的项用默认值。

- 连接本机 MySQL：只需填 DB_PASSWORD，其余保持默认即可。
- 连接远程服务器（多人共享部署）：DB_HOST 填服务器 IP，
  DB_USER / DB_PASSWORD 填服务器管理员分配的账号，
  客户端机器无需安装 MySQL。
"""

DB_HOST = "127.0.0.1"        # 数据库服务器地址（远程时填服务器 IP）
DB_PORT = 3306               # 端口，默认 3306
DB_USER = "root"             # 用户名（远程时用服务器分配的账号）
DB_PASSWORD = "你的MySQL密码"  # 密码
DB_NAME = "ledger_db"        # 数据库名（schema.sql 中创建）
