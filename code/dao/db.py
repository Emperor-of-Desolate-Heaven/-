"""数据库连接管理：统一维护与 MySQL 的连接。

连接参数按"环境变量 > config_local.py > 默认值"的顺序读取：

- 默认值面向本机 MySQL（127.0.0.1 / root / ledger_db）；
- 要在客户端机器上连接远程数据库服务器（多人共享部署），
  只需在 config_local.py 或环境变量中给出 DB_HOST 等参数，
  客户端无需安装 MySQL。
"""

import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

try:  # 本机配置（可缺省：文件不存在或未写某项时用默认值/环境变量）
    import config_local as _local  # pylint: disable=import-error
except ImportError:  # 未创建本机配置时
    _local = None


def _setting(env_key: str, local_attr: str, default: str) -> str:
    """取一项连接配置：环境变量优先，其次 config_local.py，最后默认值。"""
    value = os.environ.get(env_key)
    if value is None and _local is not None:
        value = getattr(_local, local_attr, None)
    return default if value is None else str(value)


HOST = _setting("LEDGER_DB_HOST", "DB_HOST", "127.0.0.1")
PORT = int(_setting("LEDGER_DB_PORT", "DB_PORT", "3306"))
USER = _setting("LEDGER_DB_USER", "DB_USER", "root")
PASSWORD = _setting("LEDGER_DB_PASSWORD", "DB_PASSWORD", "")
DATABASE = _setting("LEDGER_DB_NAME", "DB_NAME", "ledger_db")


@contextmanager
def get_connection():
    """建立一次数据库连接：正常结束提交，异常回滚，最后关闭。"""
    conn = pymysql.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
