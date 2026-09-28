const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { scrapeJDPrice } = require('./jd');
const { scrapeTaobaoPrice } = require('./taobao');
const { scrapeGoofishPrice } = require('./goofish');

const TARGETS_PATH = path.join(__dirname, '../data/targets.json');
const OUTPUT_PATH = path.join(__dirname, '../data/prices.json');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  console.log('=== 🚀 开始硬件全网价格精准分流采集任务 ===');

  if (!fs.existsSync(TARGETS_PATH)) {
    console.error(`未找到目标配置文件: ${TARGETS_PATH}`);
    process.exit(1);
  }

  const targets = JSON.parse(fs.readFileSync(TARGETS_PATH, 'utf-8'));
  console.log(`共读取到 ${targets.length} 款分流监控硬件。\n`);

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });

  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  const page = await context.newPage();

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
    console.log(`👉 正在处理: [${target.type?.toUpperCase() || 'NEW'}] [${target.category}] ${target.name}`);
    console.log(`   备注: ${target.notes || ''}`);

    const itemResult = {
      id: target.id,
      name: target.name,
      category: target.category,
      type: target.type,
      notes: target.notes,
      updatedAt: timestamp,
      jd: null,
      taobao: null,
      goofish: null,
    };

    // 1. 抓取京东自营价格 (新硬件优先)
    if (target.jd) {
      itemResult.jd = await scrapeJDPrice(page, target);
      await sleep(1500 + Math.random() * 1000);
    }

    // 2. 抓取闲鱼二手行情 (二手/老配件优先)
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
      type: target.type,
      jd: itemResult.jd?.price ? `￥${itemResult.jd.price}` : '-',
      goofishAvg: itemResult.goofish?.avgPrice ? `￥${itemResult.goofish.avgPrice}` : '-',
      goofishMedian: itemResult.goofish?.medianPrice ? `￥${itemResult.goofish.medianPrice}` : '-',
      taobaoMin: itemResult.taobao?.minPrice ? `￥${itemResult.taobao.minPrice}` : '-',
    });
  }

  await browser.close();

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(currentResults, null, 2), 'utf-8');
  console.log(`\n=== ✅ 分流采集任务完成！数据已更新至 ${OUTPUT_PATH} ===`);
  console.table(summary);
}

main().catch(err => {
  console.error('任务异常终止:', err);
  process.exit(1);
});
