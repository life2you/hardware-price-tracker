#!/usr/bin/env python3
"""硬件价格采集总入口 (run_tracker.py)

专注于高效、真实地采集硬件价格数据，并分批增量落库到本地 MySQL (hardware_db)。
无需解析复杂规格（后续 AI 可实时联网检索规格），核心任务是：
1. 抓取京东自营/官方现货实付价；
2. 抓取淘宝/天猫现货实付价（过滤预售定金）；
3. 抓取闲鱼二手市场价格（过滤异常标价，取中位数）；
4. 分批原子写入本地 MySQL hardware 与 price_history 表，支持随时中断，数据不丢。

用法：
    python run_tracker.py --pages 1                             # 全量 504 款挂机增量爬取入库
    python run_tracker.py --category CPU --pages 1              # 单品类抓取
    python run_tracker.py --keyword "i5-12400F" --pages 1       # 单型号抓取
    python run_tracker.py --batch-size 10                       # 每批次 10 款硬件实时落库
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

from playwright.sync_api import sync_playwright

# 导入 Product-Crawling 爬虫执行核心
import run_cpu_crawl_pw as pw
from src.storage_mysql import save_hardware_to_local_mysql

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

# 负向关键词过滤词表（彻底排除周边配件包、虚假定金与服务）
NEGATIVE_KEYWORDS = [
    "定金", "订金", "预付款", "补差价", "专拍", "链接", "配件包",
    "防尘网", "螺丝", "支架", "硅脂", "贴纸", "代装", "维修", "回收"
]

# 各品类合理买价下限（低于此价格判定为订金或配件包，直接过滤）
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
    if isinstance(data, list):
        for it in data:
            if not isinstance(it, dict):
                continue
            cat_name = it.get("category", "")
            if category and cat_name.upper() != category.upper():
                continue
            results.append({
                "id": it["id"],
                "name": it["name"],
                "category": cat_name,
                "type": it.get("type", "标准"),
                "notes": it.get("notes", "")
            })
    return results


def is_valid_price_record(title: str, price: float | None, category: str) -> bool:
    """真实买价有效性验证：排除0元、负数、品类订金异常及负向配件词"""
    if price is None or price <= 0:
        return False

    min_p = CATEGORY_MIN_PRICE.get(category, 50.0)
    if price < min_p:
        return False

    title_lower = title.lower()
    for neg in NEGATIVE_KEYWORDS:
        if neg in title_lower:
            return False

    return True


def execute_batch_crawl(
    batch_targets: list[dict],
    platforms: list[str],
    max_pages: int,
    headed: bool,
    p: Any
) -> list[dict]:
    """执行单个小批次的多平台抓取并清洗"""
    keywords = [t["name"] for t in batch_targets]
    target_by_kw = {t["name"]: t for t in batch_targets}

    batch_aggregated: dict[str, dict[str, pw.SearchResult]] = {kw: {} for kw in keywords}

    for pf_idx, pf_name in enumerate(platforms):
        if pf_idx > 0:
            time.sleep(pw.PLATFORM_DELAY_SEC)

        pf_batch_res = pw.run_platform_batch(
            p=p,
            platform=pf_name,
            keywords=keywords,
            max_pages=max_pages,
            headed=headed
        )
        for kw, sr in pf_batch_res.items():
            batch_aggregated[kw][pf_name] = sr

    updated_items = []
    now_iso = datetime.now().isoformat()

    for kw, p_map in batch_aggregated.items():
        t = target_by_kw.get(kw)
        if not t:
            continue

        item_id = t["id"]
        cat = t["category"]
        platforms_payload = {}
        all_valid_prices = []

        # 1. 清洗京东价格
        jd_res = p_map.get("jd")
        if jd_res and jd_res.success and jd_res.products:
            valid_jd = [
                p for p in jd_res.products
                if is_valid_price_record(p.title, p.current_price, cat)
            ]
            if valid_jd:
                best_jd = min(valid_jd, key=lambda x: x.current_price or 1e9)
                platforms_payload["jd"] = {
                    "price": float(best_jd.current_price),
                    "name": best_jd.title,
                    "url": best_jd.url
                }
                all_valid_prices.append((best_jd.current_price, "京东自营", best_jd.url))

        # 2. 清洗淘宝现货价格
        tb_res = p_map.get("taobao")
        if tb_res and tb_res.success and tb_res.products:
            valid_tb = [
                p for p in tb_res.products
                if is_valid_price_record(p.title, p.current_price, cat)
            ]
            if valid_tb:
                best_tb = min(valid_tb, key=lambda x: x.current_price or 1e9)
                platforms_payload["taobao"] = {
                    "price": float(best_tb.current_price),
                    "name": best_tb.title,
                    "url": best_tb.url
                }
                all_valid_prices.append((best_tb.current_price, "淘宝现货", best_tb.url))

        # 3. 清洗闲鱼二手价格 (中位数)
        xy_res = p_map.get("xianyu")
        if xy_res and xy_res.success and xy_res.products:
            valid_xy_prices = [
                p.current_price for p in xy_res.products
                if is_valid_price_record(p.title, p.current_price, cat) and p.current_price
            ]
            if valid_xy_prices:
                valid_xy_prices.sort()
                median_p = valid_xy_prices[len(valid_xy_prices) // 2]
                platforms_payload["goofish"] = {
                    "price": float(median_p),
                    "sample_count": len(valid_xy_prices)
                }

        # 4. 推荐最优到手价
        recom_payload = {}
        if all_valid_prices:
            all_valid_prices.sort(key=lambda x: x[0])
            best_val, best_plat, best_url = all_valid_prices[0]
            recom_payload = {
                "best_platform": best_plat,
                "best_price": float(best_val),
                "strategy": f"推荐在 {best_plat} 购买，实付 ￥{best_val:.0f}"
            }

        if platforms_payload:
            updated_items.append({
                "id": item_id,
                "name": t["name"],
                "category": cat,
                "type": t["type"],
                "notes": t["notes"],
                "specs": {},
                "platforms": platforms_payload,
                "recommendation": recom_payload,
                "updated_at": now_iso
            })

    return updated_items


def execute_crawl_and_save(
    targets: list[dict],
    platforms: list[str],
    max_pages: int,
    headed: bool,
    batch_size: int = 8
) -> int:
    total_targets = len(targets)
    num_batches = (total_targets + batch_size - 1) // batch_size
    logger.info(f"📋 总计采集目标: {total_targets} 款型号，拆分为 {num_batches} 个批次，每批次 {batch_size} 款增量落库")

    total_saved = 0

    with sync_playwright() as p:
        for b_idx in range(num_batches):
            start_i = b_idx * batch_size
            end_i = min(start_i + batch_size, total_targets)
            batch = targets[start_i:end_i]

            logger.info(f"▶️ 正在推进第 {b_idx + 1}/{num_batches} 批次 ({start_i + 1}~{end_i}/{total_targets})...")
            try:
                batch_updated = execute_batch_crawl(
                    batch_targets=batch,
                    platforms=platforms,
                    max_pages=max_pages,
                    headed=headed,
                    p=p
                )

                if batch_updated:
                    saved = save_hardware_to_local_mysql(batch_updated)
                    total_saved += saved
                    logger.info(f"💾 第 {b_idx + 1}/{num_batches} 批次增量落库成功！本批入库 {saved} 条，累计入库 {total_saved} 条。")
                else:
                    logger.info(f"ℹ️ 第 {b_idx + 1}/{num_batches} 批次未匹配到有效商品。")

                # 批次间适当冷却保护账号
                if b_idx < num_batches - 1:
                    logger.info("☕ 批次间保护休眠 12 秒...")
                    time.sleep(12.0)

            except Exception as e:
                logger.error(f"❌ 第 {b_idx + 1} 批次抓取发生异常: {e}", exc_info=True)
                # 单个批次异常不中断整个挂机任务，稍作休眠后继续下一批次
                time.sleep(10.0)

    logger.info(f"🏁 全量采集任务圆满完成！累计向本地 MySQL 成功写入/刷新 {total_saved} 款硬件价格！")
    return total_saved


def main() -> int:
    parser = argparse.ArgumentParser(description="硬件价格采集总入口 (本地 MySQL 增量挂机专供)")
    parser.add_argument("--category", choices=["CPU", "Motherboard", "GPU", "Cooler", "RAM", "SSD", "Case", "PSU"], help="指定抓取的品类")
    parser.add_argument("--keyword", help="指定单独抓取的硬件名称/关键词")
    parser.add_argument("--limit", type=int, default=0, help="限制抓取目标数量")
    parser.add_argument("--pages", type=int, default=1, help="每个平台爬取的页数 (默认 1 页以提升挂机效率)")
    parser.add_argument("--batch-size", type=int, default=8, help="每批增量落库的型号数量 (默认 8 款)")
    parser.add_argument("--only", choices=["jd", "taobao", "xianyu"], action="append", help="仅跑指定平台 (jd/taobao/xianyu)")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()

    if args.keyword:
        all_targets = load_targets(args.category)
        matched = None
        kw_clean = args.keyword.lower().replace(" ", "")
        for t in all_targets:
            t_clean = t["name"].lower().replace(" ", "")
            if kw_clean in t_clean or t_clean in kw_clean:
                matched = t
                break
        if matched:
            targets = [matched]
            logger.info(f"🎯 关键词 '{args.keyword}' 精准匹配到预设硬件: [{matched['id']}] {matched['name']}")
        else:
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

    platforms = args.only or ["taobao", "xianyu"] # 默认跑已完美实测的淘宝和闲鱼

    try:
        execute_crawl_and_save(
            targets=targets,
            platforms=platforms,
            max_pages=args.pages,
            headed=args.headed,
            batch_size=args.batch_size
        )
        return 0
    except KeyboardInterrupt:
        logger.warning("用户手动中止爬虫任务。")
        return 130
    except Exception as e:
        logger.error(f"爬虫执行异常: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
