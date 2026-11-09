"""用户与权限模块（组件图 SVC_Auth）：注册与登录（REQ-020）。"""

import hashlib

from dao import user_dao
from model.user import User


def _hash_password(password: str) -> str:
    """密码哈希：SHA-256，数据库只存哈希不存明文。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register(username: str, password: str) -> User:
    """注册新用户：用户名不重复、用户名与密码非空。"""
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")
    if user_dao.get_by_username(username) is not None:
        raise ValueError("用户名已存在")
    user_id = user_dao.add(username, _hash_password(password))
    return user_dao.get_by_id(user_id)


def login(username: str, password: str) -> User:
    """登录：用户名与密码匹配则返回用户，否则拒绝。"""
    user = user_dao.get_by_username(username.strip())
    if user is None or user.password != _hash_password(password):
        raise ValueError("用户名或密码错误")
    return user
