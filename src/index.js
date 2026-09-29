const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { scrapeZOLHardware } = require('./zol');
const { pushPricesToCloud } = require('./pusher');

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

  let page = await context.newPage();

  let currentResults = {};
  if (fs.existsSync(OUTPUT_PATH)) {
    try {
      currentResults = JSON.parse(fs.readFileSync(OUTPUT_PATH, 'utf-8'));
    } catch {}
  }

  const targetIds = new Set(targets.map(t => t.id));
  for (const k of Object.keys(currentResults)) {
    if (!targetIds.has(k)) {
      delete currentResults[k];
    }
  }

  const timestamp = new Date().toISOString();
  const summary = [];
  let processedCount = 0;

  for (const target of targets) {
    processedCount++;
    console.log(`----------------------------------------`);
    console.log(`👉 [${processedCount}/${targets.length}] 正在处理: [${target.type?.toUpperCase() || 'NEW'}] [${target.category}] ${target.name}`);
    if (target.notes) console.log(`   备注: ${target.notes}`);

    try {
      // 每处理 50 款硬件，重置一次 Chromium 页面上下文以彻底释放 V8 堆内存
      if (processedCount % 50 === 0 && processedCount > 0) {
        console.log(`\n🧹 [内存优化] 正在重置 Chromium 页面上下文以释放资源...`);
        try { await page.close(); } catch {}
        page = await context.newPage();
      }

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
        await sleep(800 + Math.random() * 400);
      }

      // 2. 抓取闲鱼二手流转行情 (二手或跨界对比项)
      if (target.goofish) {
        itemResult.goofish = await scrapeGoofishPrice(page, target);
        await sleep(800 + Math.random() * 400);
      }

      // 3. 智能决策与混搭建议
      const jdPrice = itemResult.zol?.jdPrice;
      const taobaoPrice = itemResult.zol?.taobaoPrice;
      const marketPrice = itemResult.zol?.marketPrice;
      const msrp = itemResult.zol?.msrp;
      const usedPrice = itemResult.goofish?.medianPrice;

      if (target.type === 'used') {
        const effectiveUsed = usedPrice || marketPrice;
        itemResult.recommendation = {
          bestChannel: '闲鱼二手',
          bestPrice: effectiveUsed,
          saving: msrp ? (msrp - (effectiveUsed || 0)) : null,
          tip: '该型号已停产或处于二手流转期，建议闲鱼/二手平台淘货',
        };
      } else if (jdPrice && marketPrice) {
        const diff = jdPrice - marketPrice;
        if (diff > 80) {
          itemResult.recommendation = {
            bestChannel: '多平台混搭/渠道现货',
            bestPrice: marketPrice,
            saving: diff,
            tip: `渠道散片/现货比京东自营便宜 ￥${diff}`,
          };
        } else {
          itemResult.recommendation = {
            bestChannel: '京东自营',
            bestPrice: jdPrice,
            saving: 0,
            tip: '差价极小或自营更优，优先选京东自营享受正品售后',
          };
        }
      } else if (jdPrice) {
        itemResult.recommendation = {
          bestChannel: '京东自营',
          bestPrice: jdPrice,
          saving: 0,
          tip: '京东自营正品现货',
        };
      } else if (taobaoPrice) {
        itemResult.recommendation = {
          bestChannel: '天猫/淘宝直达',
          bestPrice: taobaoPrice,
          saving: 0,
          tip: '品牌天猫/淘宝旗舰现货',
        };
      } else if (marketPrice) {
        itemResult.recommendation = {
          bestChannel: '主流电商/渠道商',
          bestPrice: marketPrice,
          saving: 0,
          tip: '全网渠道行情与批发参考价',
        };
      }

      currentResults[target.id] = itemResult;

      summary.push({
        硬件名称: target.name,
        品类: target.category,
        定位: target.type,
        官方参考价: msrp ? `￥${msrp}` : '-',
        全网渠道底价: marketPrice ? `￥${marketPrice}` : '-',
        京东自营价: jdPrice ? `￥${jdPrice}` : '-',
        淘宝直达价: taobaoPrice ? `￥${taobaoPrice}` : '-',
        闲鱼二手价: usedPrice ? `￥${usedPrice}` : '-',
        最佳推荐渠道: itemResult.recommendation?.bestChannel || '-',
      });

      // 每 25 款增量落盘，防意外中断
      if (processedCount % 25 === 0) {
        fs.writeFileSync(OUTPUT_PATH, JSON.stringify(currentResults, null, 2), 'utf-8');
        console.log(`💾 [增量落盘] 已保存 ${processedCount}/${targets.length} 款硬件行情数据`);
      }
    } catch (itemErr) {
      console.error(`⚠️ 处理硬件异常 [${target.name}]: ${itemErr.message}，自动跳过进入下一款`);
    }
  }

  try { await browser.close(); } catch {}

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(currentResults, null, 2), 'utf-8');
  console.log(`\n=== ✅ 全网价格精准分流采集完成！共处理 ${summary.length} 款硬件，数据已更新至 ${OUTPUT_PATH} ===\n`);

  // 打印各品类统计概览
  const catStats = {};
  summary.forEach(s => {
    if (!catStats[s.品类]) catStats[s.品类] = { 总款数: 0, 成功采价数: 0, 京东直达数: 0 };
    catStats[s.品类].总款数++;
    if (s.全网渠道底价 !== '-' || s.官方参考价 !== '-') catStats[s.品类].成功采价数++;
    if (s.京东自营价 !== '-') catStats[s.品类].京东直达数++;
  });
  console.table(catStats);

  // 抓取完成，自动向云端商业服务推送最新数据
  await pushPricesToCloud(Object.values(currentResults));
}

main().catch(err => {
  console.error('任务异常终止:', err);
  process.exit(1);
});
