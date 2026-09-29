# 开发者与维护指南 (Development Guide)

本指南旨在指导人类工程师与 AI Agent 快速搭建开发环境、运行爬虫、新增配件品类、调试反爬虫机制及同步数据。

---

## 1. 快速开始与环境要求

### 环境要求
- **Node.js**: `>= 18.0.0`
- **npm**: `>= 9.0.0`
- **操作系统**: macOS / Linux / Windows (必须在有物理显示输出或桌面环境的机器上运行以支持扫码)
- **网络环境**: 本地家庭住宅宽带（禁止在阿里云/腾讯云等机房机器运行）

### 安装依赖
```bash
cd hardware-price-tracker
npm install
npx playwright install chromium
```

---

## 2. 核心工作流与命令

### 步骤 1：获取或刷新平台登录态
闲鱼和淘宝必须登录后才能抓取，首次运行或 Cookie 过期时执行：
```bash
# 执行扫码登录，弹出可视化浏览器，手机扫码后自动保存到 state/
npm run login
```
支持交互式选择登录平台（京东、淘宝、闲鱼）。登录完成后在 `state/` 目录下生成：
- `state/jd_state.json`
- `state/taobao_state.json`
- `state/goofish_state.json`

### 步骤 2：执行行情抓取
```bash
# 全量抓取所有 504 款目标硬件
npm start

# 或者只测试单品类抓取 (通过环境变量限制)
CATEGORY=CPU npm start
```
抓取结果将实时保存在 `data/prices.json` 中。

### 步骤 3：推送行情至云端 Go 服务
```bash
# 默认推送至本地运行的 Go 服务 (http://localhost:8899)
npm run push

# 若推送到远程服务器生产环境：
CLOUD_SERVER_URL="https://your-domain.com" SYNC_SECRET_TOKEN="your-token" npm run push
```

---

## 3. 价格真实性铁律（零虚标准则）

编写或修改爬虫脚本（`src/zol.js`, `src/jd.js`, `src/taobao.js`）时，**必须严格遵守以下业务铁律**：

1. **绝对禁止记录官方发售价/指导价 (MSRP)**：
   - 官方指导价绝不能作为真实买价展示给用户；
   - 必须记录用户能在电商界面点击立即购买的实付到手价。
2. **过滤虚假低价定金**：
   - 淘宝/天猫常有“预售定金 ￥100”或“分期首付 ￥500”，爬虫必须检查页面是否存在“定金”、“预售”标签，若价格低于该品类合理下限（如 RTX 4070 标价低于 2500 元），必须作为异常值丢弃。
3. **过滤配件包与山寨配件**：
   - 检索 CPU 时常出现“防尘网”、“硅脂散热膏”等几十元的周边配件，通过标题关键词严格过滤，确保商品标题包含目标硬件核心型号。
4. **过滤停产下架僵尸高价**：
   - 老型号（如 GTX 1660 Super）官方旗舰店标价 ￥3,899 的属于无货展示，若无真实库存必须跳过，以二手平台或渠道底价为准。

---

## 4. 如何新增硬件目标

编辑 `data/targets.json`，在对应品类的 `items` 数组中追加：
```json
{
  "id": "cpu_intel_ultra5_245k",
  "name": "英特尔 酷睿 Ultra 5 245K",
  "type": "盒装/散片",
  "notes": "LGA1851 插槽，TDP 125W，Lion Cove 架构"
}
```
**规范**：
- `id` 格式为 `<品类小写>_<品牌>_<型号>`，全部小写下划线，一旦分配不得更改；
- `name` 使用国内电商最通用的标准叫法；
- `notes` 必须简明标明插槽、功耗或关键规格。

---

## 5. 调试技巧与异常排查

- **页面结构变化导致抓取价格为 0**：
  进入对应平台的爬虫脚本（如 `src/zol.js`），在抓取逻辑前临时加入 `await page.screenshot({ path: 'debug.png' })` 查看当前渲染情况，检查 DOM class 或选择器是否变更。
- **请求返回 405 / 触发滑块验证码**：
  说明当前 Session 失效或触发反爬频控。重新执行 `npm run login` 刷新登录凭证，并适当增大 `src/index.js` 中的随机睡眠等待时间（`sleep(2000)`）。
