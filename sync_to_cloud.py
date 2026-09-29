#!/usr/bin/env python3
"""云端数据同步脚本 (sync_to_cloud.py)

将 Product-Crawling (run_cpu_crawl_pw.py) 产生的多平台爬取报告与 data/targets.json 对齐，
清洗并计算各平台最优到手价，推送到硬件商业云服务 (POST /api/v1/sync/prices)。

用法：
    python sync_to_cloud.py                     # 自动寻找 logs/ 下最新的 report_pw_*.json 推送
    python sync_to_cloud.py --report logs/xxx.json
    python sync_to_cloud.py --dry-run           # 仅清洗展示，不实际发起网络推送
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
    for cat in data:
        for it in cat.get("items", []):
            mapping[it["name"].lower()] = {
                "id": it["id"],
                "name": it["name"],
                "category": cat["category"],
                "type": it.get("type", "常规"),
                "notes": it.get("notes", "")
            }
    return mapping


def match_target(target_map: dict[str, dict], keyword: str) -> dict:
    """根据搜索关键词在 targets 库中做最佳匹配"""
    kw = keyword.lower().strip()
    if kw in target_map:
        return target_map[kw]
    
    for name, item in target_map.items():
        if kw in name or name in kw:
            return item
    
    # 未匹配到则临时生成合理 ID
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
            # 优先自营
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
        "synced_at": datetime.now().isoformat(),
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
    parser = argparse.ArgumentParser(description="将 Product-Crawling 结果推送到云端服务")
    parser.add_argument("--report", help="指定的 report_pw_*.json 路径")
    parser.add_argument("--cloud-url", default=DEFAULT_CLOUD_URL, help="云端 API 地址")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="同步密钥 Token")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，不实际发起推送")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else find_latest_report()
    if not report_path or not report_path.exists():
        print(f"[WARN] 未找到有效的抓取报告文件 (logs/report_pw_*.json)。")
        print("请先运行爬虫抓取数据，例如：")
        print("    python run_cpu_crawl_pw.py \"i5-12400F\" --pages 2")
        return 1

    print(f"📖 正在读取抓取报告: {report_path}")
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    target_map = load_targets()
    normalized_items = clean_and_normalize(report_data, target_map)
    print(f"✨ 成功清洗归一化 {len(normalized_items)} 条硬件真实报价。")

    # 同时回写更新本地 data/prices.json 保证单机可用
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized_items, f, ensure_ascii=False, indent=2)
    print(f"💾 本地 data/prices.json 已同步更新。")

    if args.dry_run:
        print("🔍 [Dry-Run] 预览第一条推送数据:")
        if normalized_items:
            print(json.dumps(normalized_items[0], ensure_ascii=False, indent=2))
        return 0

    print(f"🚀 正在推送到云服务: {args.cloud_url} ...")
    success = push_to_cloud(normalized_items, args.cloud_url, args.token)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
