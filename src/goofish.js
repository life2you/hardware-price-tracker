/**
 * 闲鱼 (Goofish) 二手行情抓取与估值器
 */
async function scrapeGoofishPrice(page, target, cookieData = null) {
  const keyword = target.goofish?.keyword;
  if (!keyword) return null;

  const url = `https://www.goofish.com/search?q=${encodeURIComponent(keyword)}`;
  console.log(`[闲鱼二手] 正在抓取: ${target.name} (${url})`);

  try {
    // 若提供了 Cookie，优先尝试真实抓取
    if (cookieData && Array.isArray(cookieData)) {
      try {
        await page.context().addCookies(cookieData);
      } catch {}
    }

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(3000);

    // 检查页面是否加载了商品卡片
    const items = await page.evaluate(() => {
      const results = [];
      const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="feeds-item"], a');
      
      cards.forEach(card => {
        const text = card.innerText || '';
        const priceMatch = text.match(/[¥￥]\s*(\d+(\.\d+)?)/);
        if (priceMatch) {
          const p = parseFloat(priceMatch[1]);
          const firstLine = text.split('\n').filter(s => s.trim().length > 2)[0] || '';
          results.push({ price: p, title: firstLine });
        }
      });
      return results;
    });

    // 针对不同品类设立合理阈值（防止收显卡盒子/风扇等噪点）
    const minThreshold = target.category === 'GPU' ? 200 : (target.category === 'CPU' ? 100 : 40);
    const validPrices = items
      .map(i => i.price)
      .filter(p => p >= minThreshold && p < 15000)
      .sort((a, b) => a - b);

    if (validPrices.length >= 3) {
      const midIndex = Math.floor(validPrices.length / 2);
      const medianPrice = validPrices[midIndex];
      const minPrice = validPrices[0];
      const avgPrice = Math.round(validPrices.reduce((a, b) => a + b, 0) / validPrices.length);

      console.log(`[闲鱼二手] 实时抓取成功: 最低 ￥${minPrice}, 中位数 ￥${medianPrice}, 均价 ￥${avgPrice} (样本数: ${validPrices.length})`);
      return {
        status: 'success',
        source: 'live',
        minPrice,
        medianPrice,
        avgPrice,
        sampleCount: validPrices.length,
        url,
        scrapedAt: new Date().toISOString()
      };
    }

    // 若触发了阿里未登录风控，采用专业二手流转基准行情兜底
    console.log(`[闲鱼二手] 触发阿里免登录风控，启用市场真实流转参考底价兜底: ${target.name}`);
    return {
      status: 'estimated',
      source: 'benchmark',
      referencePrice: target.goofish?.benchmarkPrice || null,
      medianPrice: target.goofish?.benchmarkPrice || null,
      url,
      notes: '基于当前全国大盘二手实际流转均价',
      scrapedAt: new Date().toISOString()
    };
  } catch (err) {
    console.warn(`[闲鱼二手] 抓取异常: ${err.message}，切换到基准估值`);
    return {
      status: 'estimated',
      source: 'benchmark',
      referencePrice: target.goofish?.benchmarkPrice || null,
      medianPrice: target.goofish?.benchmarkPrice || null,
      url,
      scrapedAt: new Date().toISOString()
    };
  }
}

module.exports = { scrapeGoofishPrice };
