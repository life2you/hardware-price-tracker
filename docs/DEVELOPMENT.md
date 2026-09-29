# 开发者与维护指南 (Development Guide)

本指南指导开发者与 AI Agent 快速搭建 Python/Playwright 环境、使用 `Product-Crawling` 爬虫底座、排查风控与异常、以及将数据安全推送到云端服务。

---

## 1. 快速开始与环境要求

### 环境要求
- **Python**: `>= 3.9` (推荐 Python 3.10 ~ 3.12)
- **Playwright**: 必须安装 Chromium 浏览器内核
- **操作系统**: macOS / Windows / Linux (必须具备桌面图形界面以支持扫码)
- **网络环境**: 本地家庭住宅宽带（禁止在 IDC 机房服务器运行）

### 安装依赖
```bash
cd hardware-price-tracker
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 2. 核心工作流与命令

### 步骤 1：自动检测扫码登录
```bash
# 一键依次扫码登录全部平台（京东、闲鱼、淘宝）
python scripts/login_helper.py all

# 或者按需登录单平台
python scripts/login_helper.py jd
python scripts/login_helper.py xianyu
python scripts/login_helper.py taobao
```
**特点**：终端自动轮询 Cookie（`thor` / `pin` / `unb`），检测到登录成功后自动关闭浏览器并写入 `state/` 目录，无需人工按回车。

### 步骤 2：执行硬件价格抓取
```bash
# 1. 抓取单个硬件型号 (默认爬取 3 页)
python run_cpu_crawl_pw.py "i5-12400F" --pages 2

# 2. 遇到淘宝滑块时，使用 --headed 显示浏览器界面便于人工辅助
python run_cpu_crawl_pw.py "R7 7800X3D" --headed

# 3. 只跑京东自营或闲鱼单平台
python run_cpu_crawl_pw.py "RTX 4060 Ti" --only jd --pages 3
python run_cpu_crawl_pw.py "RTX 4060 Ti" --only xianyu --pages 2

# 4. 批量抓取多个硬件
python run_cpu_crawl_pw.py --keywords "9600X,7800X3D,14600KF" --pages 2
```
数据抓取完毕后，会落盘在 `logs/report_pw_<时间戳>.json`。

### 步骤 3：数据清洗并推送到 Go 云端服务
```bash
# 默认寻找最新的 report_pw_*.json，清洗并推送到本地 Go 云服务 (http://localhost:8899)
python sync_to_cloud.py

# 演练模式 (查看清洗结果与格式，不发起网络请求)
python sync_to_cloud.py --dry-run

# 推送到远程生产环境
CLOUD_SERVER_URL="https://your-domain.com" SYNC_SECRET_TOKEN="your-token" python sync_to_cloud.py
```

---

## 3. 价格真实性铁律（零虚标准则）

在维护或修改抓取抽取逻辑时，**必须严格遵守以下业务铁律**：

1. **绝对禁止记录官方发售价/指导价 (MSRP)**：
   - 官方指导价绝不能作为真实买价展示给用户；
   - 必须记录用户能在电商界面点击立即购买的实付到手价。
2. **过滤虚假低价定金**：
   - 淘宝/天猫常有“预售定金 ￥100”或“分期首付 ￥500”，若价格低于该品类合理下限（如 RTX 4070 标价低于 2500 元），必须作为异常值丢弃。
3. **过滤配件包与山寨配件**：
   - 检索 CPU 时常出现“防尘网”、“硅脂散热膏”等几十元的周边配件，通过标题关键词严格过滤，确保商品标题包含目标硬件核心型号。
4. **过滤停产下架僵尸高价**：
   - 老型号官方旗舰店标价 ￥3,899 的属于无货展示，若无真实库存必须跳过，以二手平台或渠道底价为准。

---

## 4. 排错与“睁眼”诊断机制

`Product-Crawling` 内置了完整的“睁眼”落盘诊断机制：
- **查看报错现场**：若某个平台失败，爬虫会自动将当时浏览器渲染的 HTML 网页和全屏截图保存在 `logs/debug/` 目录下（包含 URL、Title、错误堆栈）；
- **滑块与验证码**：如果日志中出现 `AntiSpiderError` 或 `rgv587_flag`，使用 `--headed` 模式重新运行，在弹出的窗口中手动拖动滑块即可。
