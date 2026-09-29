# AGENTS.md - 针对 AI 编码助手的协作与开发准则

本文件为自动化或半自动化 AI 编码助手（包括但不限于 Cursor, Claude Code, GitHub Copilot, Codex, pi-subagents 等）提供专项约束与上下文。

## 1. 核心定位与业务红线

- **核心定位**：本项目是一个基于 **[Product-Crawling (hairconker/Product-Crawling)](https://github.com/hairconker/Product-Crawling)** 的本地 Python 爬虫系统。运行在作者本机的家庭住宅宽带下，专门为云端 Go 服务供给高精度的国内电脑配件真实实付价格。
- **红线 1（绝对禁止迁移到无头机房环境）**：
  不得尝试把闲鱼、淘宝或京东的免密无头爬虫部署到云端服务器或 GitHub Actions Runner 上。国内电商机房 IP 封锁与短信滑块验证机制会立刻导致脚本报废并封禁账号。
- **红线 2（绝对禁止记录虚假 MSRP）**：
  不得引入任何“官方参考发售价”作为用户的参考买价。抓取逻辑必须保证提取的是“实付到手价”，并强制排除预售定金（如 ￥100、￥500 的订金干扰）。
- **红线 3（保护现有 504 款 target ID 命名稳定）**：
  `data/targets.json` 中的现有硬件 `id` 已与云端数据库主键、兼容性引擎紧密绑定，除非废弃，**严禁随意改动既有配件的 id 字符串**。
- **红线 4（尊重 Product-Crawling 原生架构与规范）**：
  保持 `run_cpu_crawl_pw.py`、`scripts/login_helper.py` 的架构自包含性，严禁随意删除 Stealth JS 注入、Cookie 自动回写或 `_snapshot_page` 睁眼诊断逻辑。

## 2. 核心文件与职责

- `run_cpu_crawl_pw.py`：主力 Playwright 爬虫，具备真实的 SPA 拦截、去 webdriver 特征（stealth JS）、淘宝滑块等待、闲鱼增量瀑布流抽取；
- `scripts/login_helper.py`：仅用于开发者本地可视化扫码，轮询 Cookie 自动识别登录并保存到 `state/`；
- `sync_to_cloud.py`：读取抓取报告并清洗归一化，通过 HTTP POST 推送到 Go 云端服务（`POST /api/v1/sync/prices`）；
- `data/targets.json`：504 款主流硬件规格库；
- `viewer.html`：本地抓取数据离线可视化查看页面。

## 3. 修改代码后的验证清单

每次修改或新增爬虫逻辑后，Agent 必须执行以下验收检查：
1. **Python 编译语法校验**：
   ```bash
   python3 -m py_compile run_cpu_crawl_pw.py scripts/login_helper.py sync_to_cloud.py
   ```
2. **小范围试跑验证**：
   执行单个型号抓取并演练推送：
   ```bash
   python3 sync_to_cloud.py --dry-run
   ```
3. **数据契约校验**：确认生成的 JSON 结构符合 `docs/ARCHITECTURE.md` 中的规范，特别是 `platforms`、`recommendation` 和 `updated_at`；
4. **推送联调测试**：若 Go 云服务在 `:8899` 启动，运行 `python3 sync_to_cloud.py` 并检查云端返回的 `count` 和 `200 OK` 状态。
