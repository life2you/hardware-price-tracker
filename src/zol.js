/**
 * ZOL 硬件行情与多平台电商直达提取器
 * 提供：官方指导价、市场经销商最低价、京东/淘宝真实电商直达报价与购买链接
 */
async function scrapeZOLHardware(page, target) {
  const zolUrl = target.zol?.url;
  if (!zolUrl) return null;

  console.log(`[ZOL行情分析] 正在抓取: [${target.category}] ${target.name} (${zolUrl})`);

  try {
    await page.goto(zolUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });
    await page.waitForTimeout(1500);

    const data = await page.evaluate((targetType) => {
      const title = document.querySelector('h1')?.innerText?.trim() || '';
      const bodyText = document.body ? document.body.innerText : '';
      
      // 1. 提取官方参考报价 (MSRP)
      let msrp = null;
      const msrpMatch = bodyText.match(/参考报价[：:]\s*[￥¥]?\s*(\d+)/);
      if (msrpMatch) {
        msrp = parseInt(msrpMatch[1]);
      } else {
        const altMatch = bodyText.match(/[￥¥](\d{3,6})/);
        if (altMatch) msrp = parseInt(altMatch[1]);
      }

      // 2. 提取全国经销商/渠道批发底价
      let dealerMin = null;
      const dealerMatch = bodyText.match(/商家报价[：:]\s*[￥¥]?\s*(\d+)/);
      if (dealerMatch) {
        dealerMin = parseInt(dealerMatch[1]);
      } else {
        const simpleRange = bodyText.match(/[￥¥](\d+)\s*[-~至]\s*\d+/);
        if (simpleRange) dealerMin = parseInt(simpleRange[1]);
      }

      // 3. 精确提取电商平台报价，严格区分京东与淘宝/天猫
      const mainScope = document.querySelector('.product-detail, .pro-intro, #first-screen-diy') || document.body;
      
      let jdPrice = null;
      let jdUrl = null;
      let taobaoPrice = null;
      let taobaoUrl = null;

      // 遍历所有购买与比价链接
      const buyLinks = mainScope.querySelectorAll('a');
      buyLinks.forEach(a => {
        const href = a.href || '';
        const text = (a.innerText || '').trim();
        const priceMatch = text.match(/[￥¥]\s*(\d+)/) || (a.querySelector('._j_price_num, .m-price')?.innerText || '').match(/(\d+)/);
        if (!priceMatch) return;

        const price = parseInt(priceMatch[1]);
        if (price < 50) return; // 过滤优惠券或无效金额

        const isJdLink = href.includes('jd.com') || href.includes('union-click.jd.com');
        const isTbLink = href.includes('taobao.com') || href.includes('tmall.com') || href.includes('s.click.taobao.com');
        const hasJdText = text.includes('京东');
        const hasTbText = text.includes('淘宝') || text.includes('天猫');

        if ((isJdLink || hasJdText) && !hasTbText && !isTbLink) {
          if (!jdPrice) {
            jdPrice = price;
            jdUrl = href;
          }
        } else if (isTbLink || hasTbText) {
          if (!taobaoPrice) {
            taobaoPrice = price;
            taobaoUrl = href;
          }
        }
      });

      // 4. 数据合理性熔断清洗
      // 规则 A: 停产/二手硬件 (used)，电商平台全新挂牌常为第三方僵尸死单 (如 1660 标 3899)，清空京东自营报价
      if (targetType === 'used') {
        if (jdPrice && msrp && jdPrice > msrp * 1.3) {
          jdPrice = null;
          jdUrl = null;
        }
      }

      // 规则 B: 旗舰硬件防定金/配件虚标过滤 (如 RTX 5080 发售价 8299，若电商挂 5299 则必为预售定金或配件)
      if (msrp && msrp >= 2500) {
        if (jdPrice && jdPrice < msrp * 0.65) {
          jdPrice = null; // 剔除定金异常
          jdUrl = null;
        }
        if (taobaoPrice && taobaoPrice < msrp * 0.65) {
          taobaoPrice = null; // 剔除定金异常
          taobaoUrl = null;
        }
      }

      return { title, msrp, dealerMin, jdPrice, jdUrl, taobaoPrice, taobaoUrl };
    }, target.type);

    const jdDisplay = data.jdPrice ? `￥${data.jdPrice}` : '无/已过滤';
    const tbDisplay = data.taobaoPrice ? `￥${data.taobaoPrice}` : '无/已过滤';
    console.log(`[行情解析] ${target.name} => 参考价: ￥${data.msrp || '-'}, 渠道底价: ￥${data.dealerMin || '-'}, 京东自营: ${jdDisplay}, 淘宝直达: ${tbDisplay}`);

    return {
      status: 'success',
      marketPrice: data.dealerMin || data.msrp,
      msrp: data.msrp,
      dealerMin: data.dealerMin,
      jdPrice: data.jdPrice,
      jdUrl: data.jdUrl,
      taobaoPrice: data.taobaoPrice,
      taobaoUrl: data.taobaoUrl,
      sourceUrl: zolUrl,
      scrapedAt: new Date().toISOString()
    };
  } catch (err) {
    console.error(`[ZOL行情分析] 抓取失败: ${err.message}`);
    return { status: 'failed', error: err.message };
  }
}

module.exports = { scrapeZOLHardware };
