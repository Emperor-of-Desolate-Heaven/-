"""程序入口：多人共享记账系统（实验三，命令行版）。

运行前请按 README.md 完成数据库配置（config_local.py）：
  py -3.13 main.py
"""

from presentation import login_view


def main() -> None:
    """程序入口：打印横幅后进入登录界面。"""
    print("=" * 40)
    print("多人共享记账系统（命令行版）")
    print("实验三实现 · 分层架构对应实验二组件图")
    print("=" * 40)
    login_view.main()


if __name__ == "__main__":
    main()
