# 架构设计文档 (Architecture Design)

## 1. 系统定位与核心设计哲学

`hardware-price-tracker` 是智能电脑硬件配置系统的**底层数据供给引擎**。

### 为什么采用“端云解耦”，将爬虫限制在本地？
国内主流电商平台（京东、淘宝/天猫、闲鱼、拼多多）部署了业界顶尖的风险控制与反爬虫系统：
1. **云机房 IP 污染**：阿里云、腾讯云、AWS、华为云等 IDC 机房的公网 IP 段被电商平台全量拉黑。云端发起无头浏览器请求会 100% 触发滑块验证码、短信验证或直接返回 HTTP 405/403；
2. **账号会话与风控强绑定**：闲鱼、淘宝必须登录才能检索与查看商品，而云端异地登录极易导致账号被冻结封禁；
3. **住宅 IP 本地原生运行**：利用开发者本机的家用宽带（Residential IP）配合本地 Playwright 可视化扫码登录，维持持久化的登录会话（Session Cookies / LocalStorage）。这是**零成本、长期稳定抓取国内电商数据的唯一可行路径**。

```
┌─────────────────────────────────────────────────────────────┐
│ 运行在开发者本机 (Native Residential IP / 家用宽带)            │
│                                                             │
│  [目标库 targets.json] (504款主流硬件目标)                     │
│           │                                                 │
│           ▼                                                 │
│  [扫码登录模块 src/login.js] ──> 保存至 [state/*_state.json]  │
│           │                                                 │
│           ▼                                                 │
│  [采集引擎 src/index.js]                                    │
│   ├── zol.js     (ZOL 真实市场实价 / 排除淘宝定金与虚标)      │
│   ├── jd.js      (京东自营实时现货价 / 优惠促销价)           │
│   ├── taobao.js  (天猫现货价 / 排除定金预售)                │
│   └── goofish.js (闲鱼个人二手挂牌中位数)                   │
│           │                                                 │
│           ▼                                                 │
│  [本地规整 data/prices.json] (排除虚假 MSRP，只认实付价)      │
│           │                                                 │
│           ▼                                                 │
│  [云端同步器 src/pusher.js] ──HTTP POST (Bearer Token)────> [云服务]
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 数据模型契约

### 2.1 目标库规范 (`data/targets.json`)
目标库严格限定为当前市场活跃销售的主流硬件（Intel 12~14代/Ultra 200、AMD AM4/AM5、RTX 40/50、RX 6000/7000/9000、SSD 256GB~2TB）。每一个配件必须包含唯一不可变的 `id`：

```json
{
  "category": "CPU",
  "items": [
    {
      "id": "cpu_amd_9600x",
      "name": "AMD 锐龙 5 9600X",
      "type": "盒装/散片",
      "notes": "AM5 插槽，TDP 65W，Zen5 架构"
    }
  ]
}
```

### 2.2 抓取输出规范 (`data/prices.json`)
输出必须严格执行“零虚标买价准则”，严禁将官方指导价 (MSRP) 作为售价：

```json
{
  "id": "cpu_amd_9600x",
  "name": "AMD 锐龙 5 9600X",
  "category": "CPU",
  "type": "盒装/散片",
  "notes": "AM5 插槽，TDP 65W，Zen5 架构",
  "updated_at": "2026-09-29T18:00:00.000Z",
  "platforms": {
    "jd": {
      "price": 1349.00,
      "name": "AMD 锐龙 5 9600X 盒装",
      "url": "https://item.jd.com/...",
      "stock": true
    },
    "taobao": {
      "price": 1289.00,
      "name": "AMD R5 9600X 全新散片",
      "url": "https://item.taobao.com/..."
    },
    "pdd": {
      "price": 1249.00,
      "name": "【百亿补贴】AMD 9600X"
    },
    "goofish": {
      "price": 1150.00,
      "sample_count": 18
    },
    "channel": {
      "price": 1210.00,
      "quote_source": "华强北/中关村档口现货底价"
    }
  },
  "recommendation": {
    "best_platform": "拼多多百亿补贴 / 档口散片",
    "best_price": 1210.00,
    "strategy": "CPU无假货，渠道散片/百亿补贴比京东自营便宜139元，性价比最高"
  }
}
```

---

## 3. 会话持久化与反爬机制

1. **可视化扫码登录工具 (`src/login.js`)**：
   - 启动非无头浏览器（`headless: false`），弹出真实界面由开发者使用手机 App 扫码；
   - 登录成功后，通过 `context.storageState({ path })` 将完整的 Cookies、LocalStorage 序列化保存在 `state/` 目录下；
2. **爬虫执行时载入会话 (`src/index.js`)**：
   - 抓取任务启动时通过 `browser.newContext({ storageState: 'state/jd_state.json' })` 直接继承有效登录态，无需重复登录；
3. **频率与特征对抗**：
   - 随机延迟 1.5s ~ 3.5s，模拟鼠标移动和页面滑动；
   - 抹除 `navigator.webdriver` 标记，模拟真实 User-Agent。

---

## 4. 与云服务同步协议 (`src/pusher.js`)

数据抓取完成后，通过 HTTP POST 方式一次性推送到云端 Go 服务：
- **目标端点**：`POST /api/v1/sync/prices`
- **鉴权方式**：`Authorization: Bearer <SYNC_SECRET_TOKEN>`
- **超时与重试**：单次请求超时 30 秒，失败自动重试 3 次，指数退避。
