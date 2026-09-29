# 架构设计文档 (Architecture Design)

## 1. 系统定位与开源基底

`hardware-price-tracker` 是智能电脑硬件配置系统的**底层高精度数据供给引擎**。

本项目全面以开源工业级电商爬虫 **[Product-Crawling (hairconker/Product-Crawling)](https://github.com/hairconker/Product-Crawling)** 为底层爬虫底座，并针对整机 8 大核心硬件的商业化需求进行了扩展。

```
┌─────────────────────────────────────────────────────────────┐
│ 运行在开发者本机 (Native Residential IP / 家用宽带)            │
│                                                             │
│  [目标库 data/targets.json] (504款主流硬件规格与目标)         │
│           │                                                 │
│           ▼                                                 │
│  [扫码登录保活 scripts/login_helper.py]                     │
│  自动轮询 thor/pin/unb 写入 [state/*_state.json]            │
│           │                                                 │
│           ▼                                                 │
│  [Product-Crawling 爬虫引擎 run_cpu_crawl_pw.py]            │
│   ├── 京东: SSR + api.m.jd.com XHR 响应拦截                 │
│   ├── 闲鱼: page.on('response') 拦截 mtop 结构化 JSON        │
│   └── 淘宝: 首页输入框注入 + 拦截 mtop (绕过 rgv587 硬封锁)  │
│           │                                                 │
│           ▼                                                 │
│  [生成全平台详细抓取报告 logs/report_pw_*.json]             │
│           │                                                 │
│           ▼                                                 │
│  [云端同步器 sync_to_cloud.py]                               │
│  清洗真实实付价 (排除定金) ──POST (Bearer Token)──> [Go云服务] │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 为什么爬虫必须跑在本地家用宽带？

国内主流电商平台（京东、淘宝/天猫、闲鱼）部署了业界顶尖的风控反爬虫体系：
1. **云机房 IP 污染**：阿里云、腾讯云、AWS 等 IDC 机房的公网 IP 段被电商平台全量拦截。云端发起请求会 100% 触发滑块验证码或直接阻断；
2. **账号会话与风控强绑定**：闲鱼、淘宝必须登录才能搜索，异地机房登录极易导致账号冻结；
3. **本地住宅 IP + Cookie 保活**：利用本机的原生家庭宽带配合 `Product-Crawling` 的登录态自动回写与 Cookie 保活机制，是长期稳定、零额外代理成本抓取电商数据的最佳工程路径。

---

## 3. 三大平台核心抓取与反反爬技术点

### 3.1 京东 (JD)
- **抓取路径**：HTML 骨架与 `api.m.jd.com` 接口拦截相结合；
- **反爬防御**：注入 Stealth JS 抹除 `navigator.webdriver` 自动化痕迹；
- **数据清洗**：优先匹配“自营”、“官方”标签，过滤第三方溢价僵尸商品。

### 3.2 闲鱼 (Xianyu)
- **抓取路径**：通过 Playwright 的 `page.on('response')` 拦截 `mtop.taobao.idlemtopsearch.pc.search` 接口返回；
- **瀑布流机制**：闲鱼无分页按钮，采用“滚一次 → 拦截一次 → 累加去重”策略；
- **价格清洗**：自动排除 1 元、99999 元以及异常收购标题，取有效样本的中位数作为真实二手参考价。

### 3.3 淘宝 (Taobao)
- **硬核绕过 rgv587**：直接访问 `s.taobao.com/search` 会命中阿里的硬风控 `rgv587_flag`。`Product-Crawling` 采用“打开淘宝首页暖场 → 在搜索框模拟键盘敲击 → 拦截搜索 mtop 接口”的方案，成功绕过硬封锁；
- **滑块兜底**：使用 `--headed` 模式时，遇到滑块会暂停并留出最多 5 分钟等待人工滑动。

---

## 4. 与云服务同步协议规范 (`sync_to_cloud.py`)

爬虫执行完成后，生成 `logs/report_pw_*.json`。`sync_to_cloud.py` 将其与 `data/targets.json` 对齐后发起推送：
- **目标端点**：`POST /api/v1/sync/prices`
- **认证方式**：`Authorization: Bearer <SYNC_SECRET_TOKEN>`
- **数据契约**：严格符合 `HardwareItem` 规范，自动排除定金与异常毛刺。
