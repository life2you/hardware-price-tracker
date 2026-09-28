/**
 * 京东价格抓取器 (Playwright)
 */
async function scrapeJDPrice(page, target) {
  const sku = target.jd?.sku;
  if (!sku) return null;

  const url = `https://item.jd.com/${sku}.html`;
  console.log(`[JD] 正在抓取: ${target.name} (${url})`);

  try {
    // 设置正常浏览器 Headers
    await page.setExtraHTTPHeaders({
      'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    });

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });

    // 等待价格选择器渲染 (京东常见类名: .price, .p-price, span.price)
    const priceSelector = '.p-price .price, .price, [class*="priceJd"], .summary-price-wrap .price';
    
    let priceText = null;
    try {
      await page.waitForSelector(priceSelector, { timeout: 8000 });
      priceText = await page.$eval(priceSelector, el => el.innerText.trim());
    } catch {
      // 如果 PC 页面被拦截或未渲染，尝试切到移动端 H5 链接
      console.log(`[JD] PC页未拿到价格，尝试移动端: https://item.m.jd.com/product/${sku}.html`);
      await page.goto(`https://item.m.jd.com/product/${sku}.html`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const mPriceSelector = '.price, .big-price, [class*="price"]';
      await page.waitForSelector(mPriceSelector, { timeout: 8000 });
      priceText = await page.$eval(mPriceSelector, el => el.innerText.trim());
    }

    if (priceText) {
      // 提取纯数字价格 (如 "￥729.00" -> 729)
      const match = priceText.match(/\d+(\.\d+)?/);
      if (match) {
        const price = parseFloat(match[0]);
        console.log(`[JD] 成功获取价格: ￥${price}`);
        return {
          price,
          url,
          status: 'success',
          scrapedAt: new Date().toISOString()
        };
      }
    }

    console.warn(`[JD] 未解析到数字价格: ${priceText}`);
    return { status: 'failed', error: `Unparsed: ${priceText}` };
  } catch (err) {
    console.error(`[JD] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeJDPrice };
