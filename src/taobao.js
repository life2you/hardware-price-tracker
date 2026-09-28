/**
 * 淘宝价格抓取器 (Playwright)
 */
async function scrapeTaobaoPrice(page, target) {
  const keyword = target.taobao?.keyword;
  if (!keyword) return null;

  const url = `https://s.taobao.com/search?q=${encodeURIComponent(keyword)}`;
  console.log(`[淘宝] 正在抓取: ${target.name} (${url})`);

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });

    // 检查是否被重定向到登录页
    const currentUrl = page.url();
    if (currentUrl.includes('login.taobao.com')) {
      console.warn(`[淘宝] 遇到登录拦截，跳过该项或等待后续 Cookie 支持`);
      return { status: 'blocked', error: 'Login required' };
    }

    // 淘宝搜索卡片与价格提取
    const priceSelector = '[class*="price"], .price, [class*="Price"]';
    await page.waitForSelector(priceSelector, { timeout: 8000 });

    const prices = await page.evaluate(() => {
      const results = [];
      const els = document.querySelectorAll('[class*="priceInt"], [class*="price"], [class*="Price"]');
      els.forEach(el => {
        const text = el.innerText || '';
        const match = text.match(/\d+(\.\d+)?/);
        if (match) {
          const val = parseFloat(match[0]);
          if (val > 50 && val < 20000) results.push(val);
        }
      });
      return results;
    });

    if (prices.length > 0) {
      prices.sort((a, b) => a - b);
      const minPrice = prices[0];
      const medianPrice = prices[Math.floor(prices.length / 2)];
      console.log(`[淘宝] 成功获取价格: 最低 ￥${minPrice}, 参考中位数 ￥${medianPrice}`);
      return {
        status: 'success',
        minPrice,
        medianPrice,
        url,
        scrapedAt: new Date().toISOString()
      };
    }

    return { status: 'failed', error: 'No price elements matched' };
  } catch (err) {
    console.error(`[淘宝] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeTaobaoPrice };
