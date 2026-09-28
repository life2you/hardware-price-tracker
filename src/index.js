const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { scrapeZOLHardware } = require('./zol');
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
    if (target.notes) console.log(`   备注: ${target.notes}`);

    const itemResult = {
      id: target.id,
      name: target.name,
      category: target.category,
      type: target.type,
      notes: target.notes,
      updatedAt: timestamp,
      zol: null,
      goofish: null,
      recommendation: null,
    };

    // 1. 抓取 ZOL 硬件官方/渠道底价与京东报价
    if (target.zol) {
      itemResult.zol = await scrapeZOLHardware(page, target);
      await sleep(1000 + Math.random() * 500);
    }

    // 2. 抓取闲鱼二手流转行情 (二手或跨界对比项)
    if (target.goofish) {
      itemResult.goofish = await scrapeGoofishPrice(page, target);
      await sleep(1000 + Math.random() * 500);
    }

    // 3. 智能决策与混搭建议
    const jdPrice = itemResult.zol?.jdPrice;
    const marketPrice = itemResult.zol?.marketPrice;
    const usedPrice = itemResult.goofish?.medianPrice;

    if (target.type === 'used' && usedPrice) {
      itemResult.recommendation = {
        bestChannel: '闲鱼二手',
        bestPrice: usedPrice,
        saving: jdPrice ? (jdPrice - usedPrice) : null,
        tip: '老配件停产/溢价，闲鱼淘二手性价比最高',
      };
    } else if (marketPrice && jdPrice) {
      const diff = jdPrice - marketPrice;
      if (diff > 50) {
        itemResult.recommendation = {
          bestChannel: '多平台混搭/淘宝渠道',
          bestPrice: marketPrice,
          saving: diff,
          tip: `散片/渠道渠道比京东省 ￥${diff}`,
        };
      } else {
        itemResult.recommendation = {
          bestChannel: '京东自营',
          bestPrice: jdPrice,
          saving: 0,
          tip: '差价极小，优先选京东自营售后保修',
        };
      }
    } else if (jdPrice) {
      itemResult.recommendation = {
        bestChannel: '京东自营',
        bestPrice: jdPrice,
        saving: 0,
        tip: '京东自营正品现货',
      };
    }

    currentResults[target.id] = itemResult;

    summary.push({
      硬件名称: target.name,
      品类: target.category,
      定位: target.type,
      官方参考价: itemResult.zol?.msrp ? `￥${itemResult.zol.msrp}` : '-',
      全网渠道底价: itemResult.zol?.marketPrice ? `￥${itemResult.zol.marketPrice}` : '-',
      京东自营价: itemResult.zol?.jdPrice ? `￥${itemResult.zol.jdPrice}` : '-',
      闲鱼二手价: itemResult.goofish?.medianPrice ? `￥${itemResult.goofish.medianPrice}` : '-',
      最佳推荐渠道: itemResult.recommendation?.bestChannel || '-',
    });
  }

  await browser.close();

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(currentResults, null, 2), 'utf-8');
  console.log(`\n=== ✅ 全网价格精准分流采集完成！数据已更新至 ${OUTPUT_PATH} ===\n`);
  console.table(summary);
}

main().catch(err => {
  console.error('任务异常终止:', err);
  process.exit(1);
});
