"""用户表数据访问（对应类图：用户）。"""

from typing import Optional

from dao.db import get_connection
from model.user import User


def _row_to_user(row: dict) -> User:
    """把查询结果行转换为 User 实体。"""
    return User(
        user_id=row["user_id"],
        username=row["username"],
        password=row["password"],
        created_at=row["created_at"],
    )


def add(username: str, password_hash: str) -> int:
    """新增用户，返回新用户 ID。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO `user` (username, password) VALUES (%s, %s)",
                (username, password_hash),
            )
            return cur.lastrowid


def get_by_username(username: str) -> Optional[User]:
    """按用户名查询用户，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM `user` WHERE username = %s", (username,)
            )
            row = cur.fetchone()
            return _row_to_user(row) if row else None


def get_by_id(user_id: int) -> Optional[User]:
    """按用户 ID 查询用户，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM `user` WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            return _row_to_user(row) if row else None
