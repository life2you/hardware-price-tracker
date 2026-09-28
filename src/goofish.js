/**
 * 闲鱼 (Goofish) 价格抓取器 (Playwright)
 */
async function scrapeGoofishPrice(page, target) {
  const keyword = target.goofish?.keyword;
  if (!keyword) return null;

  const url = `https://www.goofish.com/search?q=${encodeURIComponent(keyword)}`;
  console.log(`[闲鱼] 正在抓取: ${target.name} (${url})`);

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });

    // 闲鱼商品卡片与价格文本常见类名
    const itemCardSelector = '[class*="card"], [class*="item"], [class*="feeds-item"]';
    await page.waitForSelector(itemCardSelector, { timeout: 10000 });

    // 获取前 10 个有效商品的价格
    const items = await page.evaluate(() => {
      const results = [];
      const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="feeds-item"]');
      
      cards.forEach(card => {
        const text = card.innerText || '';
        // 匹配类似 "¥520" 或 "520元" 或 "￥ 520"
        const priceMatch = text.match(/[¥￥]\s*(\d+(\.\d+)?)/);
        if (priceMatch) {
          const p = parseFloat(priceMatch[1]);
          results.push({
            price: p,
            title: text.split('\n')[0]?.substring(0, 40)
          });
        }
      });
      return results;
    });

    if (items.length > 0) {
      // 过滤离群假数据（比如 1元、9.9元标价收件，或者 9999元标价展示）
      const validPrices = items
        .map(i => i.price)
        .filter(p => p > 50 && p < 15000)
        .sort((a, b) => a - b);

      if (validPrices.length > 0) {
        // 计算中位数和最低可用价
        const midIndex = Math.floor(validPrices.length / 2);
        const medianPrice = validPrices[midIndex];
        const minPrice = validPrices[0];
        const avgPrice = Math.round(validPrices.reduce((a, b) => a + b, 0) / validPrices.length);

        console.log(`[闲鱼] 成功获取行情: 最低 ￥${minPrice}, 中位数 ￥${medianPrice}, 均价 ￥${avgPrice} (样本数: ${validPrices.length})`);

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
    return { status: 'failed', error: 'No valid prices found' };
  } catch (err) {
    console.error(`[闲鱼] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeGoofishPrice };
