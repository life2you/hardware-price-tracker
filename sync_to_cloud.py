#!/usr/bin/env python3
"""云端数据同步脚本 (sync_to_cloud.py)

默认从本地 MySQL (hardware_db) 捞取最新硬件与价格数据，推送到远端商业云服务 (POST /api/v1/sync/prices)。
也支持从本地 report_pw_*.json 报告或 data/prices.json 提取推送。

用法：
    python sync_to_cloud.py                     # 默认从本地 MySQL 读取全部已持久化硬件推送到云端
    python sync_to_cloud.py --category CPU      # 只推送本地 MySQL 中的某一品类
    python sync_to_cloud.py --source report     # 从最新的 report_pw_*.json 清洗推送
    python sync_to_cloud.py --dry-run           # 仅展示数据，不发起实际网络请求
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS_FILE = ROOT / "data" / "targets.json"
PRICES_FILE = ROOT / "data" / "prices.json"
LOG_DIR = ROOT / "logs"

DEFAULT_CLOUD_URL = os.getenv("CLOUD_SERVER_URL", "http://localhost:8899")
DEFAULT_TOKEN = os.getenv("SYNC_SECRET_TOKEN", "pc-tracker-secret-2026")


def find_latest_report() -> Path | None:
    reports = sorted(glob.glob(str(LOG_DIR / "report_pw_*.json")), reverse=True)
    if reports:
        return Path(reports[0])
    return None


def load_targets() -> dict[str, dict]:
    """加载 504 款主流硬件配置，生成 name -> target_item 映射"""
    if not TARGETS_FILE.exists():
        return {}
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    mapping = {}
    if isinstance(data, list):
        for it in data:
            if not isinstance(it, dict):
                continue
            if "items" in it and isinstance(it["items"], list):
                cat_name = it.get("category", "")
                for sub_it in it["items"]:
                    mapping[sub_it["name"].lower()] = {
                        "id": sub_it["id"],
                        "name": sub_it["name"],
                        "category": cat_name,
                        "type": sub_it.get("type", "常规"),
                        "notes": sub_it.get("notes", "")
                    }
            else:
                cat_name = it.get("category", "")
                mapping[it["name"].lower()] = {
                    "id": it["id"],
                    "name": it["name"],
                    "category": cat_name,
                    "type": it.get("type", "常规"),
                    "notes": it.get("notes", "")
                }
    return mapping


def match_target(target_map: dict[str, dict], keyword: str) -> dict:
    kw = keyword.lower().strip()
    if kw in target_map:
        return target_map[kw]

    for name, item in target_map.items():
        if kw in name or name in kw:
            return item

    clean_id = "hw_" + "".join(c if c.isalnum() else "_" for c in kw.lower())
    return {
        "id": clean_id,
        "name": keyword,
        "category": "CPU",
        "type": "通用",
        "notes": ""
    }


def clean_and_normalize(report_data: dict, target_map: dict[str, dict]) -> list[dict]:
    items = []
    results = report_data.get("results", {})

    for kw, platforms in results.items():
        matched = match_target(target_map, kw)
        item_id = matched["id"]
        category = matched["category"]
        name = matched["name"]

        plat_payload = {}
        all_prices = []

        # 1. 处理京东
        jd_res = platforms.get("jd", {})
        if jd_res.get("success") and jd_res.get("products"):
            jd_prods = jd_res["products"]
            valid_jd = [p for p in jd_prods if p.get("current_price") and p["current_price"] > 100]
            if valid_jd:
                best_jd = min(valid_jd, key=lambda x: x["current_price"])
                plat_payload["jd"] = {
                    "price": float(best_jd["current_price"]),
                    "name": best_jd.get("title", name),
                    "url": best_jd.get("detail_url", "")
                }
                all_prices.append((best_jd["current_price"], "京东自营"))

        # 2. 处理淘宝
        tb_res = platforms.get("taobao", {})
        if tb_res.get("success") and tb_res.get("products"):
            tb_prods = tb_res["products"]
            valid_tb = [p for p in tb_prods if p.get("current_price") and p["current_price"] > 100]
            if valid_tb:
                best_tb = min(valid_tb, key=lambda x: x["current_price"])
                plat_payload["taobao"] = {
                    "price": float(best_tb["current_price"]),
                    "name": best_tb.get("title", name),
                    "url": best_tb.get("detail_url", "")
                }
                all_prices.append((best_tb["current_price"], "淘宝现货"))

        # 3. 处理闲鱼二手
        xy_res = platforms.get("xianyu", {})
        if xy_res.get("success") and xy_res.get("products"):
            xy_prods = xy_res["products"]
            valid_xy = [p["current_price"] for p in xy_prods if p.get("current_price") and p["current_price"] > 80]
            if valid_xy:
                valid_xy.sort()
                mid_price = valid_xy[len(valid_xy) // 2]
                plat_payload["goofish"] = {
                    "price": float(mid_price),
                    "sample_count": len(valid_xy)
                }

        recom = {}
        if all_prices:
            all_prices.sort(key=lambda x: x[0])
            recom = {
                "best_price": float(all_prices[0][0]),
                "best_platform": all_prices[0][1],
                "strategy": f"全网比价推荐在 {all_prices[0][1]} 购买，实付 ￥{all_prices[0][0]:.0f} 元"
            }

        items.append({
            "id": item_id,
            "name": name,
            "category": category,
            "type": matched.get("type", "标准"),
            "notes": matched.get("notes", ""),
            "platforms": plat_payload,
            "recommendation": recom,
            "updated_at": datetime.now().isoformat()
        })

    return items


def push_to_cloud(items: list[dict], cloud_url: str, token: str) -> bool:
    url = f"{cloud_url.rstrip('/')}/api/v1/sync/prices"
    payload = {
        "synced_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8")
            print(f"✅ 云端推送成功 (HTTP {resp.status}): {resp_body}")
            return True
    except Exception as e:
        print(f"❌ 云端推送失败: {e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="将本地硬件数据推送到云端商业服务")
    parser.add_argument("--source", choices=["mysql", "report", "json"], default="mysql", help="数据源 (默认优先从本地 mysql 读取)")
    parser.add_argument("--category", choices=["CPU", "Motherboard", "GPU", "Cooler", "RAM", "SSD", "Case", "PSU"], help="限定推送的品类")
    parser.add_argument("--report", help="若指定 --source report，指定的 report_pw_*.json 路径")
    parser.add_argument("--cloud-url", default=DEFAULT_CLOUD_URL, help="云端 API 地址")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="同步密钥 Token")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，不实际发起推送")
    args = parser.parse_args()

    items = []

    # 1. 默认优先从本地 MySQL 读取
    if args.source == "mysql":
        try:
            from src.storage_mysql import load_hardware_from_local_mysql
            items = load_hardware_from_local_mysql(args.category)
            print(f"🗄️  已从本地 MySQL (hardware_db) 捞取 {len(items)} 条已持久化硬件行情。")
        except Exception as e:
            print(f"⚠️  从本地 MySQL 读取失败 ({e})，尝试回退到本地 JSON 快照...")
            args.source = "json"

    # 2. 回退从本地 data/prices.json 读取
    if args.source == "json" and not items:
        if PRICES_FILE.exists():
            with open(PRICES_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    items = list(d.values())
                else:
                    items = d
            if args.category:
                items = [it for it in items if it.get("category", "").upper() == args.category.upper()]
            print(f"💾 从本地 data/prices.json 读取到 {len(items)} 条记录。")
        else:
            print("❌ 未找到本地 data/prices.json")
            return 1

    # 3. 从临时爬取报告中读取
    if args.source == "report":
        report_path = Path(args.report) if args.report else find_latest_report()
        if not report_path or not report_path.exists():
            print(f"[WARN] 未找到有效的抓取报告文件 (logs/report_pw_*.json)。")
            return 1
        print(f"📖 正在读取抓取报告: {report_path}")
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        target_map = load_targets()
        items = clean_and_normalize(report_data, target_map)
        print(f"✨ 成功清洗归一化 {len(items)} 条硬件真实报价。")

    if not items:
        print("⚠️ 没有需要推送的数据。")
        return 0

    if args.dry_run:
        print("🔍 [Dry-Run] 预览第一条推送数据:")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
        return 0

    print(f"🚀 正在推送到云服务: {args.cloud_url} (共 {len(items)} 条)...")
    success = push_to_cloud(items, args.cloud_url, args.token)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
