#!/usr/bin/env python3
"""硬件价格追踪总控入口 (run_tracker.py)

基于 Product-Crawling 改造的工业级硬件价格追踪总入口。
整合 targets.json (8大品类504款型号)，调度 Playwright 拦截爬虫，执行真实买价清洗过滤，
自动生成 data/prices.json，并支持一键推送到 Go 云端服务。

常用命令：
    python run_tracker.py --category CPU --pages 2       # 抓取 CPU 品类最新行情
    python run_tracker.py --category GPU --pages 2       # 抓取显卡品类最新行情
    python run_tracker.py --keyword "9600X"              # 抓取单型号
    python run_tracker.py --category CPU --push          # 抓取完成后自动推送到云端服务
    python run_tracker.py --headed                       # 弹出浏览器界面 (过滑块用)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 导入 Product-Crawling 的底层爬虫核心
import run_cpu_crawl_pw as pw_crawler
from sync_to_cloud import push_to_cloud

ROOT = Path(__file__).resolve().parent
TARGETS_FILE = ROOT / "data" / "targets.json"
PRICES_FILE = ROOT / "data" / "prices.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("tracker")

# 负向关键词过滤词表（彻底排除周边配件包、虚假订金与服务）
NEGATIVE_KEYWORDS = [
    "定金", "订金", "预付款", "补差价", "专拍", "链接", "配件包",
    "防尘网", "螺丝", "支架", "硅脂", "贴纸", "代装", "维修", "回收"
]

# 品类合理单价下限（低于此价格判定为定金或配件包，直接过滤）
CATEGORY_MIN_PRICE = {
    "CPU": 200.0,
    "GPU": 500.0,
    "Motherboard": 200.0,
    "Cooler": 30.0,
    "RAM": 80.0,
    "SSD": 100.0,
    "Case": 60.0,
    "PSU": 100.0
}


def load_targets(category: str | None = None) -> list[dict]:
    if not TARGETS_FILE.exists():
        logger.error(f"未找到目标硬件配置文件: {TARGETS_FILE}")
        return []
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for cat_block in data:
        cat_name = cat_block.get("category")
        if category and cat_name.upper() != category.upper():
            continue
        for it in cat_block.get("items", []):
            results.append({
                "id": it["id"],
                "name": it["name"],
                "category": cat_name,
                "type": it.get("type", "标准"),
                "notes": it.get("notes", "")
            })
    return results


def is_valid_product(title: str, price: float | None, category: str, keyword: str) -> bool:
    """真实买价过滤器：排除虚假预售定金、周边配件、异常诱导低价"""
    if price is None or price <= 0:
        return False

    min_price = CATEGORY_MIN_PRICE.get(category, 50.0)
    if price < min_price:
        return False

    # 排除负向词
    for neg in NEGATIVE_KEYWORDS:
        if neg in title:
            return False

    return True


def crawl_targets(
    targets: list[dict],
    platforms: list[str],
    max_pages: int,
    headed: bool,
    auto_push: bool,
    cloud_url: str,
    token: str
) -> None:
    logger.info(f"🚀 开始采集硬件行情：共 {len(targets)} 款型号，平台: {platforms}，每平台 {max_pages} 页")

    # 载入现有 prices.json，支持增量合并
    prices_map = {}
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, "r", encoding="utf-8") as f:
                old_list = json.load(f)
                for it in old_list:
                    prices_map[it["id"]] = it
        except Exception:
            pass

    keywords = [t["name"] for t in targets]
    target_by_kw = {t["name"]: t for t in targets}

    # 调用 Product-Crawling 的 Playwright 核心
    crawl_results = pw_crawler.crawl_multi_keywords_pw(
        keywords=keywords,
        platforms=platforms,
        max_pages=max_pages,
        headed=headed
    )

    # 清洗并更新到标准格式
    updated_items = []
    for kw, p_results in crawl_results.items():
        t = target_by_kw.get(kw)
        if not t:
            continue

        item_id = t["id"]
        cat = t["category"]
        existing = prices_map.get(item_id, {
            "id": item_id,
            "name": t["name"],
            "category": cat,
            "type": t["type"],
            "notes": t["notes"],
            "platforms": {},
            "recommendation": {}
        })

        plat_payload = existing.get("platforms", {})
        all_valid_prices = []

        # 1. 清洗京东数据
        if "jd" in p_results and p_results["jd"].success:
            jd_prods = p_results["jd"].products
            valid_jd = [
                p for p in jd_prods
                if is_valid_product(p.title, p.current_price, cat, kw)
            ]
            if valid_jd:
                # 优先挑出自营且价格最低
                best_jd = min(valid_jd, key=lambda x: x.current_price)
                plat_payload["jd"] = {
                    "price": float(best_jd.current_price),
                    "name": best_jd.title,
                    "url": best_jd.url,
                    "stock": True
                }
                all_valid_prices.append((best_jd.current_price, "京东自营", best_jd.url))

        # 2. 清洗淘宝天猫数据
        if "taobao" in p_results and p_results["taobao"].success:
            tb_prods = p_results["taobao"].products
            valid_tb = [
                p for p in tb_prods
                if is_valid_product(p.title, p.current_price, cat, kw)
            ]
            if valid_tb:
                best_tb = min(valid_tb, key=lambda x: x.current_price)
                plat_payload["taobao"] = {
                    "price": float(best_tb.current_price),
                    "name": best_tb.title,
                    "url": best_tb.url
                }
                all_valid_prices.append((best_tb.current_price, "天猫/淘宝现货", best_tb.url))

        # 3. 清洗闲鱼二手数据 (求合理中位数)
        if "xianyu" in p_results and p_results["xianyu"].success:
            xy_prods = p_results["xianyu"].products
            valid_xy = [
                p.current_price for p in xy_prods
                if is_valid_product(p.title, p.current_price, cat, kw)
            ]
            if valid_xy:
                valid_xy.sort()
                median_price = valid_xy[len(valid_xy) // 2]
                plat_payload["goofish"] = {
                    "price": float(median_price),
                    "sample_count": len(valid_xy)
                }

        # 4. 生成综合省钱购买建议
        if all_valid_prices:
            all_valid_prices.sort(key=lambda x: x[0])
            best_p, best_plat, best_u = all_valid_prices[0]
            existing["recommendation"] = {
                "best_platform": best_plat,
                "best_price": float(best_p),
                "strategy": f"推荐在 {best_plat} 入手，当前实付到手价 ￥{best_p:.0f} 元"
            }

        existing["platforms"] = plat_payload
        existing["updated_at"] = datetime.now().isoformat()
        prices_map[item_id] = existing
        updated_items.append(existing)

    # 回写到本地 data/prices.json
    all_final_list = list(prices_map.values())
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_final_list, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 本地 data/prices.json 更新完成，累计已维护 {len(all_final_list)} 款硬件价格行情。")

    # 自动推送到云端服务
    if auto_push and updated_items:
        logger.info(f"🚀 正在将最新采集的 {len(updated_items)} 条行情推送到云端服务 ({cloud_url})...")
        push_to_cloud(updated_items, cloud_url, token)


def main() -> int:
    parser = argparse.ArgumentParser(description="硬件价格追踪总控 (基于 Product-Crawling 改造)")
    parser.add_argument("--category", choices=["CPU", "Motherboard", "GPU", "Cooler", "RAM", "SSD", "Case", "PSU"], help="指定抓取的品类")
    parser.add_argument("--keyword", help="指定单独抓取的硬件名称/关键词")
    parser.add_argument("--limit", type=int, default=0, help="最多抓取目标数量 (调试用)")
    parser.add_argument("--pages", type=int, default=2, help="每个平台爬取的页数 (默认 2 页)")
    parser.add_argument("--only", choices=["jd", "taobao", "xianyu"], action="append", help="仅跑指定电商平台")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口 (便于调试或过滑块)")
    parser.add_argument("--push", action="store_true", help="抓取完成后自动推送到云端服务")
    parser.add_argument("--cloud-url", default=os.getenv("CLOUD_SERVER_URL", "http://localhost:8899"), help="云端 API 地址")
    parser.add_argument("--token", default=os.getenv("SYNC_SECRET_TOKEN", "pc-tracker-secret-2026"), help="云端同步 Token")
    args = parser.parse_args()

    # 选定抓取目标
    if args.keyword:
        targets = [{
            "id": "hw_" + re.sub(r"\W+", "_", args.keyword.lower()),
            "name": args.keyword,
            "category": args.category or "CPU",
            "type": "通用",
            "notes": ""
        }]
    else:
        targets = load_targets(args.category)

    if not targets:
        logger.error("未找到符合条件的抓取目标！")
        return 1

    if args.limit > 0:
        targets = targets[:args.limit]

    platforms = args.only or ["jd", "taobao", "xianyu"]

    try:
        crawl_targets(
            targets=targets,
            platforms=platforms,
            max_pages=args.pages,
            headed=args.headed,
            auto_push=args.push,
            cloud_url=args.cloud_url,
            token=args.token
        )
        return 0
    except KeyboardInterrupt:
        logger.warning("用户主动中止爬取。")
        return 130
    except Exception as e:
        logger.error(f"执行爬取任务失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
