#!/usr/bin/env python3
"""本地 MySQL 存储层 (storage_mysql.py)

负责将爬虫采集到的真实价格原子落库到本地 MySQL (hardware_db)，
沉淀完整的历史行情走势，并提供数据读取接口供同步器推送到远端云服务。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    pymysql = None

logger = logging.getLogger("storage_mysql")

DEFAULT_HOST = os.getenv("LOCAL_MYSQL_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("LOCAL_MYSQL_PORT", "3306"))
DEFAULT_USER = os.getenv("LOCAL_MYSQL_USER", "root")
DEFAULT_PASSWORD = os.getenv("LOCAL_MYSQL_PASSWORD", "123456")
DEFAULT_DB = os.getenv("LOCAL_MYSQL_DATABASE", "hardware_db")


def get_connection():
    if pymysql is None:
        raise RuntimeError("pymysql 未安装，请执行: python3 -m pip install pymysql --user --break-system-packages")
    return pymysql.connect(
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        user=DEFAULT_USER,
        password=DEFAULT_PASSWORD,
        database=DEFAULT_DB,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False
    )


def init_mysql_tables() -> None:
    """自动创建 hardware 与 price_history 数据表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hardware (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(64) NOT NULL,
                    type VARCHAR(32) NOT NULL,
                    notes VARCHAR(500),
                    specs_json JSON,
                    platforms_json JSON,
                    recommendation_json JSON,
                    updated_at DATETIME NOT NULL,
                    INDEX idx_category (category),
                    INDEX idx_updated_at (updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    hardware_id VARCHAR(64) NOT NULL,
                    platform VARCHAR(32) NOT NULL,
                    price DECIMAL(10, 2) NOT NULL,
                    recorded_at DATETIME NOT NULL,
                    INDEX idx_hw_date (hardware_id, recorded_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
        conn.commit()
    finally:
        conn.close()


def normalize_hardware_item(it: dict[str, Any]) -> dict[str, Any]:
    """统一字段格式，兼容新旧格式与 ZOL 数据"""
    item_id = it.get("id") or it.get("itemId")
    name = it.get("name") or it.get("title") or item_id
    category = it.get("category", "CPU")
    h_type = it.get("type", "标准")
    notes = it.get("notes", "")

    # 处理 platforms
    platforms = it.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}

    # 如果有 zol 节点，转换填充到 platforms
    zol = it.get("zol")
    if isinstance(zol, dict) and zol.get("status") == "success":
        if "jd" not in platforms and zol.get("jdPrice"):
            platforms["jd"] = {
                "price": float(zol["jdPrice"]),
                "name": name,
                "url": zol.get("jdUrl", "")
            }
        if "channel" not in platforms and zol.get("dealerMin"):
            platforms["channel"] = {
                "price": float(zol["dealerMin"]),
                "name": name,
                "quote_source": "档口渠道底价"
            }

    # 处理 recommendation
    recom = it.get("recommendation")
    if not isinstance(recom, dict):
        recom = {}
    elif "bestChannel" in recom:
        recom = {
            "best_platform": recom.get("bestChannel"),
            "best_price": recom.get("bestPrice"),
            "strategy": recom.get("tip", "")
        }

    return {
        "id": item_id,
        "name": name,
        "category": category,
        "type": h_type,
        "notes": notes,
        "specs": it.get("specs", {}),
        "platforms": platforms,
        "recommendation": recom,
        "updated_at": it.get("updated_at") or it.get("updatedAt")
    }


def save_hardware_to_local_mysql(raw_items: list[dict[str, Any]] | dict[str, Any]) -> int:
    """原子性批量保存到本地 MySQL"""
    if not raw_items:
        return 0

    if isinstance(raw_items, dict):
        items_list = list(raw_items.values())
    else:
        items_list = list(raw_items)

    init_mysql_tables()
    conn = get_connection()
    saved_count = 0

    try:
        with conn.cursor() as cursor:
            upsert_sql = """
                INSERT INTO hardware (
                    id, name, category, type, notes,
                    specs_json, platforms_json, recommendation_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    category = VALUES(category),
                    type = VALUES(type),
                    notes = VALUES(notes),
                    specs_json = VALUES(specs_json),
                    platforms_json = VALUES(platforms_json),
                    recommendation_json = VALUES(recommendation_json),
                    updated_at = VALUES(updated_at)
            """

            history_sql = """
                INSERT INTO price_history (hardware_id, platform, price, recorded_at)
                VALUES (%s, %s, %s, %s)
            """

            now = datetime.now()
            for raw_it in items_list:
                if not isinstance(raw_it, dict):
                    continue
                it = normalize_hardware_item(raw_it)
                if not it["id"]:
                    continue

                specs_str = json.dumps(it.get("specs", {}), ensure_ascii=False)
                platforms = it.get("platforms", {})
                platforms_str = json.dumps(platforms, ensure_ascii=False)
                recom_str = json.dumps(it.get("recommendation", {}), ensure_ascii=False)

                updated_at_val = it.get("updated_at")
                if not updated_at_val:
                    updated_time = now
                elif isinstance(updated_at_val, str):
                    try:
                        updated_time = datetime.fromisoformat(updated_at_val.replace("Z", "+00:00"))
                    except Exception:
                        updated_time = now
                else:
                    updated_time = now

                cursor.execute(upsert_sql, (
                    it["id"],
                    it["name"],
                    it.get("category", "CPU"),
                    it.get("type", "标准"),
                    it.get("notes", ""),
                    specs_str,
                    platforms_str,
                    recom_str,
                    updated_time.strftime("%Y-%m-%d %H:%M:%S")
                ))
                saved_count += 1

                # 记录价格历史快照 (用于绘制趋势图)
                for plat_name, p_info in platforms.items():
                    if isinstance(p_info, dict) and "price" in p_info and p_info["price"]:
                        try:
                            p_val = float(p_info["price"])
                            if p_val > 0:
                                cursor.execute(history_sql, (
                                    it["id"], plat_name, p_val, updated_time.strftime("%Y-%m-%d %H:%M:%S")
                                ))
                        except (ValueError, TypeError):
                            pass

        conn.commit()
        logger.info(f"✅ 成功将 {saved_count} 款硬件与最新报价保存到本地 MySQL (hardware_db)")
        return saved_count
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 本地 MySQL 写入失败: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def load_hardware_from_local_mysql(category: str | None = None) -> list[dict[str, Any]]:
    """从本地 MySQL 读取已持久化的硬件与价格数据，供推送器使用"""
    init_mysql_tables()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = "SELECT id, name, category, type, notes, specs_json, platforms_json, recommendation_json, updated_at FROM hardware"
            params = []
            if category:
                query += " WHERE category = %s"
                params.append(category)
            query += " ORDER BY updated_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            items = []
            for r in rows:
                specs = r["specs_json"]
                if isinstance(specs, str) and specs:
                    specs = json.loads(specs)
                elif not specs:
                    specs = {}

                platforms = r["platforms_json"]
                if isinstance(platforms, str) and platforms:
                    platforms = json.loads(platforms)
                elif not platforms:
                    platforms = {}

                recom = r["recommendation_json"]
                if isinstance(recom, str) and recom:
                    recom = json.loads(recom)
                elif not recom:
                    recom = {}

                if hasattr(r["updated_at"], "strftime"):
                    updated_at_str = r["updated_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
                elif hasattr(r["updated_at"], "isoformat"):
                    updated_at_str = r["updated_at"].isoformat() + "Z"
                else:
                    updated_at_str = str(r["updated_at"]) + "Z"

                items.append({
                    "id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "type": r["type"],
                    "notes": r["notes"],
                    "specs": specs,
                    "platforms": platforms,
                    "recommendation": recom,
                    "updated_at": updated_at_str
                })
            return items
    finally:
        conn.close()
