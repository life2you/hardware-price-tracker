/**
 * 京东价格抓取器 (Playwright)
 */
async function scrapeJDPrice(page, target) {
  const sku = target.jd?.sku;
  if (!sku) return null;

  const url = `https://item.jd.com/${sku}.html`;
  console.log(`[JD] 正在抓取: ${target.name} (${url})`);

  try {
    await page.setExtraHTTPHeaders({
      'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    });

    // 优先尝试移动端 H5 链接（在海外与自动化环境中更稳定、体积更小、更少拦截）
    const mobileUrl = `https://item.m.jd.com/product/${sku}.html`;
    await page.goto(mobileUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });

    // 等待 DOM 挂载价格元素（使用 attached 而非 visible，防止遮罩层阻碍）
    const selector = '.price, .big-price, [id*="price"], [class*="price"]';
    await page.waitForSelector(selector, { state: 'attached', timeout: 8000 });

    // 从页面中提取所有价格候选，找到最合理的数字
    const extractedPrices = await page.evaluate(() => {
      const candidates = [];
      const els = document.querySelectorAll('.price, .big-price, [id*="price"], [class*="price"]');
      for (const el of els) {
        const text = (el.innerText || '').replace(/,/g, '').trim();
        const match = text.match(/\d+(\.\d+)?/);
        if (match) {
          const val = parseFloat(match[0]);
          if (val > 10 && val < 50000) {
            candidates.push(val);
          }
        }
      }
      return candidates;
    });

    if (extractedPrices.length > 0) {
      // 京东价格通常在主价格区域，取最前排的有效价格
      const price = extractedPrices[0];
      console.log(`[JD] 成功获取价格: ￥${price}`);
      return {
        price,
        url,
        status: 'success',
        scrapedAt: new Date().toISOString()
      };
    }

    console.warn(`[JD] 未解析到合理数字价格`);
    return { status: 'failed', error: 'No price matched in DOM' };
  } catch (err) {
    console.error(`[JD] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeJDPrice };
