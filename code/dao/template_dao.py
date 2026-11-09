"""场景模板表数据访问（对应类图：场景模板）。"""

from typing import Optional

from dao.db import get_connection
from model.scene_template import SceneTemplate


def _row_to_template(row: dict) -> SceneTemplate:
    """把查询结果行转换为 SceneTemplate 实体（默认类别由逗号串拆为列表）。"""
    return SceneTemplate(
        template_id=row["template_id"],
        template_type=row["template_type"],
        default_categories=row["default_category"].split(","),
        settle_method=row["settle_method"],
        budget_caliber=row["budget_caliber"],
    )


def list_all() -> list[SceneTemplate]:
    """查询全部场景模板（旅行 / 合租 / 家庭）。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM scene_template ORDER BY template_id")
            return [_row_to_template(row) for row in cur.fetchall()]


def get_by_id(template_id: int) -> Optional[SceneTemplate]:
    """按模板 ID 查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM scene_template WHERE template_id = %s",
                (template_id,),
            )
            row = cur.fetchone()
            return _row_to_template(row) if row else None


def get_by_type(template_type: str) -> Optional[SceneTemplate]:
    """按模板类型（旅行 / 合租 / 家庭）查询，不存在返回 None。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM scene_template WHERE template_type = %s",
                (template_type,),
            )
            row = cur.fetchone()
            return _row_to_template(row) if row else None
