"""表现层公共工具：会话、输入解析、菜单循环、业务异常转提示（本层专用）。"""

# pylint: disable=duplicate-code  # 菜单循环骨架与各视图的定制循环天然相似

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional


@dataclass
class Session:
    """当前登录用户（登录成功后在各界面间传递）。"""

    user_id: int = 0
    username: str = ""


def pause() -> None:
    """按回车继续。"""
    input("\n按回车继续…")


def input_str(prompt: str, default: str = "") -> str:
    """输入一行文本（去两端空白）；空输入返回默认值。"""
    raw = input(prompt).strip()
    return raw if raw else default


def input_int(prompt: str) -> Optional[int]:
    """输入整数；空输入返回 None，非数字重新询问。"""
    while True:
        raw = input_str(prompt)
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            print("请输入数字")


def input_datetime(
    prompt: str, default: Optional[datetime] = None
) -> datetime:
    """输入时间（年-月-日 时:分）；空输入取默认值。"""
    default_text = default.strftime("%Y-%m-%d %H:%M") if default else ""
    while True:
        raw = input_str(prompt, default_text)
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            print("时间格式应为 年-月-日 时:分，如 2026-11-09 14:30")


def confirm(prompt: str) -> bool:
    """是/否确认。"""
    return input_str(prompt + "（y/n）").lower() in ("y", "yes", "是")


def run(action: Callable, *args, **kwargs) -> tuple[bool, Any]:
    """执行一个业务动作：业务异常转成一行提示，不再向上抛出。

    视图统一用它调用 service：成功返回 (True, 返回值)，
    失败返回 (False, None) 并已打印"操作失败：原因"。
    """
    try:
        result = action(*args, **kwargs)
    except (ValueError, PermissionError) as exc:
        print(f"操作失败：{exc}")
        return False, None
    return True, result


def menu(title: str, items: list[tuple[str, Callable]]) -> None:
    """菜单循环：每项为 (名称, 处理函数)；输入 0 返回上级。"""
    while True:
        print(f"\n===== {title} =====")
        for i, (label, _) in enumerate(items, 1):
            print(f"  {i}. {label}")
        print("  0. 返回")
        choice = input_int("请选择：")
        if choice is None:
            continue
        if choice == 0:
            return
        if 1 <= choice <= len(items):
            items[choice - 1][1]()
        else:
            print("无效选项")
