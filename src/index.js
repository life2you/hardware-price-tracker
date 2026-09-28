const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { scrapeJDPrice } = require('./jd');
const { scrapeTaobaoPrice } = require('./taobao');
const { scrapeGoofishPrice } = require('./goofish');

const TARGETS_PATH = path.join(__dirname, '../data/targets.json');
const OUTPUT_PATH = path.join(__dirname, '../data/prices.json');

// 随机等待，降低反爬封控概率
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  console.log('=== 🚀 开始硬件全网价格自动采集任务 ===');

  if (!fs.existsSync(TARGETS_PATH)) {
    console.error(`未找到目标配置文件: ${TARGETS_PATH}`);
    process.exit(1);
  }

  const targets = JSON.parse(fs.readFileSync(TARGETS_PATH, 'utf-8'));
  console.log(`共读取到 ${targets.length} 款监控硬件配置。\n`);

  // 启动 Playwright 无头浏览器
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled', // 隐藏 WebDriver 自动化标记
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });

  // 抹除 navigator.webdriver 标识
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  const page = await context.newPage();

  // 读取已有的历史价格，以便做增量合并
  let currentResults = {};
  if (fs.existsSync(OUTPUT_PATH)) {
    try {
      currentResults = JSON.parse(fs.readFileSync(OUTPUT_PATH, 'utf-8'));
    } catch {}
  }

  const timestamp = new Date().toISOString();
  const summary = [];

  for (const target of targets) {
    console.log(`----------------------------------------`);
    console.log(`👉 正在处理硬件: [${target.category}] ${target.name}`);

    const itemResult = {
      id: target.id,
      name: target.name,
      category: target.category,
      updatedAt: timestamp,
      jd: null,
      taobao: null,
      goofish: null,
    };

    // 1. 抓取京东自营价格
    if (target.jd) {
      itemResult.jd = await scrapeJDPrice(page, target);
      await sleep(1500 + Math.random() * 1000);
    }

    // 2. 抓取闲鱼二手行情
    if (target.goofish) {
      itemResult.goofish = await scrapeGoofishPrice(page, target);
      await sleep(1500 + Math.random() * 1000);
    }

    // 3. 抓取淘宝价格
    if (target.taobao) {
      itemResult.taobao = await scrapeTaobaoPrice(page, target);
      await sleep(1500 + Math.random() * 1000);
    }

    currentResults[target.id] = itemResult;
    summary.push({
      name: target.name,
      jd: itemResult.jd?.price || 'N/A',
      goofishAvg: itemResult.goofish?.avgPrice || 'N/A',
      taobaoMin: itemResult.taobao?.minPrice || 'N/A',
    });
  }

  await browser.close();

  // 写入并持久化结果
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(currentResults, null, 2), 'utf-8');
  console.log(`\n=== ✅ 采集任务完成！数据已更新至 ${OUTPUT_PATH} ===`);
  console.table(summary);
}

main().catch(err => {
  console.error('任务异常终止:', err);
  process.exit(1);
});
