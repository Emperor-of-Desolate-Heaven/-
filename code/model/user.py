"""用户实体（类图：用户）。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """系统用户：登录后可加入一个或多个账本。

    注册、登录等业务逻辑在 service/auth_service 中实现，
    本类只承载用户数据（类图中的 +登录()、+注册() 属于业务层行为）。
    """

    user_id: Optional[int] = None
    username: str = ""
    password: str = ""  # SHA-256 哈希，不保存明文
    created_at: Optional[datetime] = None
