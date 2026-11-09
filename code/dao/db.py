"""数据库连接管理：统一维护与本机 MySQL 的连接。

连接参数优先从环境变量读取，其次读取本机配置文件 config_local.py
（该文件保存数据库密码，已被 git 忽略，不进公开仓库）。
"""

import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

try:  # 本机密码配置，缺失时回退为环境变量或空密码
    from config_local import DB_PASSWORD as _LOCAL_PASSWORD  # pylint: disable=import-error
except ImportError:  # 未创建本机配置时
    _LOCAL_PASSWORD = ""

HOST = os.environ.get("LEDGER_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("LEDGER_DB_PORT", "3306"))
USER = os.environ.get("LEDGER_DB_USER", "root")
PASSWORD = os.environ.get("LEDGER_DB_PASSWORD", _LOCAL_PASSWORD)
DATABASE = os.environ.get("LEDGER_DB_NAME", "ledger_db")


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
