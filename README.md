# 🖥️ Hardware Price Tracker (基于 Product-Crawling 的本地电商真实买价采集与同步引擎)

本项目基于开源工业级电商爬虫 **[Product-Crawling (hairconker/Product-Crawling)](https://github.com/hairconker/Product-Crawling)** 构建，专为 PC 智能硬件配置系统提供精准的**真实无虚标到手价**。

通过**本地家庭住宅宽带（Residential IP）**、**Playwright 自动化框架**与**登录态自动保活机制**，精准绕过国内主流电商（京东、闲鱼、淘宝）对云机房 IP 的封锁，自动抓取全网真实价格，并无缝同步推送给云端 Go 业务服务。

---

## 📚 完整项目与开发文档导航

为了方便人类工程师与外部 AI Agent（Cursor、Claude Code、Codex 等）独立接管本项目开发，请查阅以下专门文档：

- 🏛️ **[架构设计文档 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md)**：深入了解为什么爬虫必须限制在本地、反爬与会话持久化机制、数据契约规范及云端推送协议。
- 🛠️ **[开发者与维护指南 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md)**：包含 Python/Playwright 环境搭建、扫码登录操作、单品/批量抓取命令、以及真实买价（排除虚假定金/配件包）的业务铁律。
- 🤖 **[AI 编码助手准则 (AGENTS.md)](AGENTS.md)**：给后续接入的 AI Agent 设定的开发准则、红线约束与验收测试清单。
- 📖 **[CLAUDE.md](CLAUDE.md)**：Product-Crawling 原生架构与规范指南。

---

## 🌟 核心特性与平台策略

- **底座来自成熟开源项目**：完整复用 `Product-Crawling` 的 Playwright SPA、mtop 拦截与反风控体系；
- **京东 (JD)**：从 HTML 骨架 + `api.m.jd.com` XHR 拦截商品 JSON，优先提取自营与真实促销价；
- **闲鱼 (Xianyu)**：`page.on('response')` 监听 `mtop.taobao.idlemtopsearch.pc.search` 返回，瀑布流增量抽取并计算市场中位数；
- **淘宝 (Taobao)**：首页搜索框输入 + 拦截 mtop 响应，**彻底绕过 `rgv587` 硬封锁**；
- **自动检测扫码登录 (`scripts/login_helper.py`)**：轮询 `thor/pin` (京东) 或 `unb/tracknick` (阿里系) 关键 Cookie，扫码即走，无需人工回车；
- **云端数据同步器 (`sync_to_cloud.py`)**：将抓取报告与 504 款硬件库匹配，清洗规整后通过 Bearer Token 原子推送到 Go 云端服务。

---

## 📁 目录结构

```text
hardware-price-tracker/
├── AGENTS.md                  # 给 AI Agent 的开发规则与修改红线
├── CLAUDE.md                  # Product-Crawling 原生规范
├── docs/                      # 架构设计、开发指南与问卷原型
├── data/
│   ├── targets.json           # 504 款主流硬件目标库 (含规格备忘)
│   └── prices.json            # 本地最新的全平台真实到手价格
├── scripts/
│   └── login_helper.py        # 扫码登录助手 (京东 / 闲鱼 / 淘宝)
├── run_cpu_crawl_pw.py        # 主力 Playwright 爬虫 (mtop 拦截 / 批量搜索)
├── sync_to_cloud.py           # 抓取结果清洗并推送到 Go 云服务
├── viewer.html                # 本地离线数据可视化查看器
├── requirements.txt           # Python 依赖
└── package.json               # npm 脚本便捷包装
```

---

## 🚀 极速上手

### 1. 安装 Python 依赖
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. 扫码登录（生成持久化 Cookie）
```bash
# 登录全部 3 个平台（京东、闲鱼、淘宝）
python scripts/login_helper.py all

# 或者只登录其中某一个平台
python scripts/login_helper.py jd
python scripts/login_helper.py xianyu
python scripts/login_helper.py taobao
```
在弹出的浏览器中手机扫码，终端自动检测 Cookie 并保存到 `state/` 目录。

### 3. 开始抓取
```bash
# 全品类抓取
python run_tracker.py

# 按指定品类抓取（例如只抓显卡或 CPU，抓完自动推送到云端）
python run_tracker.py --category GPU --push
python run_tracker.py --category CPU --push

# 抓取单个硬件测试
python run_tracker.py --keyword "9600X" --headed
```
爬取完成后，详细数据会自动保存在 `logs/report_pw_*.json`。

### 4. 清洗并推送到 Go 云端服务
```bash
# 自动抓取最新生成的 report_pw_*.json 并推送到本地 Go 云服务 (:8899)
python sync_to_cloud.py

# 演练预览，不实际发起推送
python sync_to_cloud.py --dry-run

# 推送到远程服务器
CLOUD_SERVER_URL="https://your-domain.com" SYNC_SECRET_TOKEN="your-token" python sync_to_cloud.py
```
