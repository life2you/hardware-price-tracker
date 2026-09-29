/**
 * ZOL 硬件行情与京东直链提取器
 * 提供：官方指导价、市场经销商最低价、京东实时报价与购买链接
 */
async function scrapeZOLHardware(page, target) {
  const zolUrl = target.zol?.url;
  if (!zolUrl) return null;

  console.log(`[ZOL/京东] 正在抓取: ${target.name} (${zolUrl})`);

  try {
    await page.goto(zolUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });
    await page.waitForTimeout(1500);

    const data = await page.evaluate(() => {
      const title = document.querySelector('h1')?.innerText?.trim() || '';
      const bodyText = document.body ? document.body.innerText : '';
      
      // 1. 提取官方参考报价
      let msrp = null;
      const msrpMatch = bodyText.match(/参考报价[：:]\s*[￥¥]?\s*(\d+)/);
      if (msrpMatch) {
        msrp = parseInt(msrpMatch[1]);
      } else {
        const altMatch = bodyText.match(/[￥¥](\d{3,6})/);
        if (altMatch) msrp = parseInt(altMatch[1]);
      }

      // 2. 提取经销商底价（如 ¥2124-3119 或 商家报价：¥701 或 商家报价：¥229）
      let dealerMin = null;
      const dealerMatch = bodyText.match(/商家报价[：:]\s*[￥¥]?\s*(\d+)/);
      if (dealerMatch) {
        dealerMin = parseInt(dealerMatch[1]);
      } else {
        const simpleRange = bodyText.match(/[￥¥](\d+)\s*[-~至]\s*\d+/);
        if (simpleRange) dealerMin = parseInt(simpleRange[1]);
      }

      // 3. 提取京东官方/直达价格与购买链接 (限制在商品主详情区域内，避免侧边栏或搭配推荐干扰)
      const mainScope = document.querySelector('.product-detail, .pro-intro, #first-screen-diy');
      let jdPrice = null;
      let jdUrl = null;

      if (mainScope) {
        let jdEl = mainScope.querySelector('a._j_price_jd, a.new-shop-go, a.link_jd, ._j_price_jd');
        if (!jdEl) {
          jdEl = mainScope.querySelector('.price__b2c a[href*="jd.com"], .price_commerce a[href*="jd.com"]');
        }

        if (jdEl) {
          jdUrl = jdEl.href;
          const container = jdEl.closest('.price__b2c, .price_commerce, .select-mol') || jdEl;
          const priceNumEl = container.querySelector('._j_price_num, .m-price, em');
          const rawText = priceNumEl ? priceNumEl.innerText : jdEl.innerText;
          const match = rawText.match(/[￥¥]\s*(\d+)/) || rawText.match(/(\d{3,6})/);
          if (match) {
            const val = parseInt(match[1]);
            // 过滤异常过低的配件/优惠券价格
            if (val >= 100) jdPrice = val;
          }
        }
      }

      return { title, msrp, dealerMin, jdPrice, jdUrl };
    });

    console.log(`[ZOL/京东] 成功解析: ${target.name} => 参考价: ￥${data.msrp}, 渠道底价: ￥${data.dealerMin || '无'}, 京东自营: ￥${data.jdPrice || '无'}`);

    return {
      status: 'success',
      marketPrice: data.dealerMin || data.msrp,
      msrp: data.msrp,
      dealerMin: data.dealerMin,
      jdPrice: data.jdPrice,
      jdUrl: data.jdUrl,
      sourceUrl: zolUrl,
      scrapedAt: new Date().toISOString()
    };
  } catch (err) {
    console.error(`[ZOL/京东] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeZOLHardware };
