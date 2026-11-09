"""登录界面（组件图 UI_Login）：注册与登录（REQ-020）。"""

import sys

from presentation import ledger_view
from presentation.console import Session, input_str, menu, run
from service import auth_service


def main() -> None:
    """登录主循环：登录成功后进入"我的账本"，退出登录回到本菜单。"""
    menu("登录 / 注册", [
        ("登录", _login),
        ("注册", _register),
        ("退出系统", lambda: sys.exit(0)),
    ])


def _register() -> None:
    print("\n-- 注册 --")
    username = input_str("用户名：")
    if not username:
        print("用户名不能为空")
        return
    password = input_str("密码：")
    if not password:
        print("密码不能为空")
        return
    if password != input_str("确认密码："):
        print("两次输入的密码不一致")
        return
    ok, user = run(auth_service.register, username, password)
    if ok:
        print(f"注册成功，欢迎 {user.username}！请登录。")


def _login() -> None:
    print("\n-- 登录 --")
    username = input_str("用户名：")
    password = input_str("密码：")
    if not username or not password:
        print("用户名和密码不能为空")
        return
    ok, user = run(auth_service.login, username, password)
    if ok:
        print(f"登录成功，欢迎 {user.username}！")
        ledger_view.main(
            Session(user_id=user.user_id, username=user.username)
        )
