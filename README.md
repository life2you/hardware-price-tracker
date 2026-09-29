# 🖥️ Hardware Price Tracker (本地硬件价格采集与云端同步引擎)

基于 **Node.js + Playwright** 构建的本地电商真实买价采集与云端同步系统。

本项目利用**开发者本地原生家用宽带（Residential IP）**与**可视化扫码登录持久化机制**，精准绕过国内主流电商平台（京东、淘宝/天猫、闲鱼、拼多多）对机房公网 IP 的风控拉黑，抓取真实无虚标的实付到手价，并定时同步推送给云端 Go 业务服务。

---

## 📚 完整项目与开发文档导航

为了方便人类工程师与外部 AI Agent（Cursor、Claude Code、Codex 等）独立接管本项目开发，请查阅以下专门文档：

- 🏛️ **[架构设计文档 (docs/ARCHITECTURE.md)](docs/ARCHITECTURE.md)**：深入了解为什么爬虫必须限制在本地、反爬与会话持久化机制、数据契约规范及云端推送协议。
- 🛠️ **[开发者与维护指南 (docs/DEVELOPMENT.md)](docs/DEVELOPMENT.md)**：包含本地开发环境安装、扫码登录操作、单品类调试抓取、如何新增硬件、以及真实买价（排除虚假定金/配件包）的业务铁律。
- 🤖 **[AI 编码助手准则 (AGENTS.md)](AGENTS.md)**：给后续接入的 AI Agent 设定的开发准则、红线约束与验收测试清单。

---

## 🌟 核心特性

- **本地原生住宅 IP 驱动**：彻底杜绝云服务器机房 IP 触发短信验证码、滑块阻断或封号；
- **可视化扫码登录工具 (`npm run login`)**：支持京东、淘宝、闲鱼会话一键持久化保存到 `state/`，长期免登；
- **504 款主流硬件全覆盖**：覆盖 CPU、主板、显卡、散热、内存、固态、机箱、电源 8 大核心品类；
- **零 MSRP 真实买价准则**：全面杜绝官方发售价，抓取用户实际能买到的到手价，过滤淘宝预售定金、分期首付及无货僵尸价；
- **端云数据推送器 (`src/pusher.js`)**：内置 Bearer Token 安全认证与重试机制，采集完成即刻原子性推送到云端服务。

---

## 📁 目录结构

```text
hardware-price-tracker/
├── AGENTS.md            # 给 AI Agent 的开发规则与修改红线
├── docs/
│   ├── ARCHITECTURE.md  # 系统架构设计、会话持久化设计与推送契约
│   └── DEVELOPMENT.md   # 快速开发指南、调试技巧与数据真实性铁律
├── data/
│   ├── targets.json     # 504 款主流硬件目标库 (含规格备忘)
│   └── prices.json      # 实时抓取的全平台真实实付价格明细
├── state/               # 本地扫码登录生成的 Session Cookie (已忽略防泄漏)
├── src/
│   ├── login.js         # 本地可视化交互式扫码登录工具
│   ├── zol.js           # 中关村在线真实行情清洗 (防御预售定金)
│   ├── jd.js            # 京东自营现货与促销价提取
│   ├── taobao.js        # 淘宝/天猫现货价格提取
│   ├── goofish.js       # 闲鱼二手个人挂牌中位数提取
│   ├── pusher.js        # 云端 Go 服务安全数据推送器
│   └── index.js         # 采集调度主入口
├── package.json
└── README.md
```

---

## 🚀 极速上手

### 1. 安装依赖
```bash
npm install
npx playwright install chromium
```

### 2. 扫码登录（首次或 Cookie 失效时）
```bash
npm run login
```
在弹出的浏览器中用手机扫码登录京东/淘宝/闲鱼，登录态将自动写入 `state/` 目录。

### 3. 开始抓取
```bash
# 全量抓取
npm start

# 或单品类测试抓取
CATEGORY=CPU npm start
```

### 4. 推送数据到云服务
```bash
# 推送到本地 Go 服务 (端口 8899)
npm run push

# 推送到远程服务器
CLOUD_SERVER_URL="https://your-domain.com" SYNC_SECRET_TOKEN="your-token" npm run push
```
