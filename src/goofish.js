/**
 * 闲鱼 (Goofish) 价格抓取器 (Playwright)
 */
async function scrapeGoofishPrice(page, target) {
  const keyword = target.goofish?.keyword;
  if (!keyword) return null;

  const url = `https://www.goofish.com/search?q=${encodeURIComponent(keyword)}`;
  console.log(`[闲鱼] 正在抓取: ${target.name} (${url})`);

  try {
    // 关键修复：改用 domcontentloaded，避免 networkidle 永远等待 websocket 超时
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });

    // 给异步卡片列表 3 秒渲染时间
    await page.waitForTimeout(3000);

    const items = await page.evaluate(() => {
      const results = [];
      // 遍历所有可能的卡片或文本块
      const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="feeds-item"], a');
      
      cards.forEach(card => {
        const text = card.innerText || '';
        // 查找如 "¥ 520"、"¥520.00"、"520元"
        const priceMatch = text.match(/[¥￥]\s*(\d+(\.\d+)?)/);
        if (priceMatch) {
          const p = parseFloat(priceMatch[1]);
          // 初步清洗单行标题
          const firstLine = text.split('\n').filter(s => s.trim().length > 3)[0] || '';
          results.push({ price: p, title: firstLine });
        }
      });
      return results;
    });

    if (items.length > 0) {
      // 过滤离群低价（收卡贴如 "1元"、"99元收"）和离群高价（"9999元展示"）
      // 针对不同类目设立最低合理门槛
      const minThreshold = target.category === 'GPU' ? 300 : (target.category === 'CPU' ? 100 : 50);

      const validPrices = items
        .map(i => i.price)
        .filter(p => p >= minThreshold && p < 20000)
        .sort((a, b) => a - b);

      if (validPrices.length > 0) {
        // 取中位数与去噪均价
        const midIndex = Math.floor(validPrices.length / 2);
        const medianPrice = validPrices[midIndex];
        const minPrice = validPrices[0];
        const avgPrice = Math.round(validPrices.reduce((a, b) => a + b, 0) / validPrices.length);

        console.log(`[闲鱼] 成功获取行情: 最低 ￥${minPrice}, 中位数 ￥${medianPrice}, 均价 ￥${avgPrice} (有效样本: ${validPrices.length})`);

        return {
          status: 'success',
          minPrice,
          medianPrice,
          avgPrice,
          sampleCount: validPrices.length,
          url,
          scrapedAt: new Date().toISOString()
        };
      }
    }

    console.warn(`[闲鱼] 未匹配到足够的价格样本`);
    return { status: 'failed', error: 'No valid prices found after filtering' };
  } catch (err) {
    console.error(`[闲鱼] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeGoofishPrice };
