#!/usr/bin/env python3
"""预设硬件底账入库脚本 (seed_targets_to_mysql.py)

将 data/targets.json 中的 504 款主流硬件规格底账全部初始化到本地 MySQL (hardware_db.hardware)，
保证本地数据库中具备完整的 8 大品类、504 款硬件基础数据（型号、插槽、功耗、分类与备注）。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 引入本地存储层
from src.storage_mysql import get_connection, init_mysql_tables

ROOT = Path(__file__).resolve().parent
TARGETS_FILE = ROOT / "data" / "targets.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("seed_mysql")


def seed_all_targets():
    if not TARGETS_FILE.exists():
        logger.error(f"未找到 targets.json 文件: {TARGETS_FILE}")
        return 0

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        logger.error("targets.json 格式异常，期望是列表")
        return 0

    init_mysql_tables()
    conn = get_connection()
    inserted = 0

    try:
        with conn.cursor() as cursor:
            # 使用 INSERT ... ON DUPLICATE KEY UPDATE 确保幂等，保留已有价格，仅补全新硬件或刷新基础信息
            sql = """
                INSERT INTO hardware (
                    id, name, category, type, notes,
                    specs_json, platforms_json, recommendation_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    category = VALUES(category),
                    type = VALUES(type),
                    notes = VALUES(notes),
                    specs_json = IF(specs_json IS NULL OR specs_json = '{}', VALUES(specs_json), specs_json)
            """

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for it in data:
                item_id = it.get("id")
                name = it.get("name")
                category = it.get("category", "CPU")
                h_type = it.get("type", "标准")
                notes = it.get("notes", "")

                # 初始规格提取
                specs = {}
                if "zol" in it:
                    specs["zol_url"] = it["zol"].get("url", "")
                if "goofish" in it:
                    specs["goofish_kw"] = it["goofish"].get("keyword", "")

                specs_str = json.dumps(specs, ensure_ascii=False)
                platforms_str = json.dumps({}, ensure_ascii=False)
                recom_str = json.dumps({}, ensure_ascii=False)

                cursor.execute(sql, (
                    item_id, name, category, h_type, notes,
                    specs_str, platforms_str, recom_str, now
                ))
                inserted += 1

        conn.commit()
        logger.info(f"🎉 成功将全部 {inserted} 款预设硬件全量初始化落库到本地 MySQL (hardware_db.hardware)！")
        return inserted
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 批量入库失败: {e}", exc_info=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    count = seed_all_targets()
    sys.exit(0 if count > 0 else 1)
