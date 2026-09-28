# 🖥️ Hardware Price Tracker (全网硬件价格与闲鱼行情监控)

基于 **Playwright 无头浏览器** 和 **GitHub Actions** 的全自动化硬件价格追踪系统。

每天定时无感监控 **京东自营全新价**、**淘宝/天猫最低价** 以及 **闲鱼二手参考均价**，自动将数据写入 `data/prices.json` 并提交持久化。

---

## 🌟 核心特性

- **多平台比价**：同时覆盖京东（JD）、淘宝（Taobao）与闲鱼二手（Goofish）；
- **闲鱼二手行情算法**：自动清洗异常收卡/诈骗标价，计算真实二手市场中位数与均价；
- **0 服务器成本**：完全依托 GitHub Actions 免费算力每天定时执行；
- **为个人主页赋能**：你的前端网站直接读取本仓库生成的 `data/prices.json`，即可拥有全网最优混搭比价能力。

---

## 📁 目录结构

```text
hardware-price-tracker/
├── .github/workflows/
│   └── tracker.yml      # GitHub Actions 每日定时执行工作流 (支持手动触发)
├── data/
│   ├── targets.json     # 监控的硬件清单 (可随意增减 CPU、显卡、主板)
│   └── prices.json      # 自动化脚本抓取并更新的最新价格结果
├── src/
│   ├── jd.js            # 京东自营价格抓取器
│   ├── goofish.js       # 闲鱼二手行情抓取器
│   ├── taobao.js        # 淘宝价格抓取器
│   └── index.js         # 自动化调度主入口
├── package.json
└── README.md
```

---

## 🛠️ 本地运行与调试

```bash
# 安装依赖
npm install

# 安装 Playwright 浏览器内核
npx playwright install chromium

# 运行抓取
npm start
```

---

## 🚀 部署到 GitHub Actions

只要将代码推送到你的 GitHub 仓库，GitHub Actions 就会在每天**北京时间凌晨 04:00** 自动启动无头浏览器抓取，并将最新的 `prices.json` 自动 commit 回仓库！

你也可以进入 GitHub 仓库页面的 **Actions -> Daily Hardware Price Tracker -> 点击 Run workflow** 随时手动测试。
