/**
 * 数据推送模块
 * 将本地爬虫清洗后的全网硬件多平台价格，推送到远端 Go 云商业服务
 */
const fs = require('fs');
const path = require('path');

const CLOUD_URL = process.env.CLOUD_SERVER_URL || 'http://localhost:8899';
const SYNC_TOKEN = process.env.SYNC_SECRET_TOKEN || 'pc-tracker-secret-2026';
const PRICES_PATH = path.resolve(__dirname, '../data/prices.json');

async function pushPricesToCloud(items) {
  let hardwareList = items;
  if (!hardwareList && fs.existsSync(PRICES_PATH)) {
    try {
      const raw = JSON.parse(fs.readFileSync(PRICES_PATH, 'utf-8'));
      hardwareList = Object.values(raw);
    } catch (e) {
      console.error(`读取 ${PRICES_PATH} 失败: ${e.message}`);
      return false;
    }
  }

  if (!hardwareList || hardwareList.length === 0) {
    console.warn(`[推送服务] 暂无有效硬件价格数据可供同步`);
    return false;
  }

  const endpoint = `${CLOUD_URL.replace(/\/+$/, '')}/api/v1/sync/prices`;
  console.log(`\n📡 [数据推送] 正在向云端服务同步行情数据...`);
  console.log(`   - 目标端点: ${endpoint}`);
  console.log(`   - 同步款数: ${hardwareList.length} 款硬件`);

  const payload = {
    synced_at: new Date().toISOString(),
    count: hardwareList.length,
    items: hardwareList.map(it => ({
      id: it.id,
      name: it.name,
      category: it.category,
      type: it.type || 'new',
      notes: it.notes || '',
      platforms: it.platforms || {
        jd: it.zol?.jdPrice ? { price: it.zol.jdPrice, type: '京东自营', url: it.zol.jdUrl, updated_at: it.updatedAt } : null,
        taobao: it.zol?.taobaoPrice ? { price: it.zol.taobaoPrice, type: '天猫/淘宝现货', url: it.zol.taobaoUrl, updated_at: it.updatedAt } : null,
        goofish: it.goofish?.medianPrice ? { price: it.goofish.medianPrice, type: '闲鱼二手流转均价', updated_at: it.updatedAt } : null,
        channel: it.zol?.dealerMin ? { price: it.zol.dealerMin, type: '档口批发散片底价', updated_at: it.updatedAt } : null,
      },
      recommendation: it.recommendation ? {
        best_platform: it.recommendation.bestChannel || it.recommendation.best_platform || '全网优选',
        best_price: it.recommendation.bestPrice || it.recommendation.best_price || 0,
        saving: it.recommendation.saving || 0,
        tip: it.recommendation.tip || '',
      } : {
        best_platform: '暂无推荐',
        best_price: 0,
        saving: 0,
        tip: '',
      },
      updated_at: it.updatedAt || new Date().toISOString(),
    })),
  };

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${SYNC_TOKEN}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errText = await res.text();
      console.error(`❌ [数据推送失败] HTTP ${res.status}: ${errText}`);
      return false;
    }

    const data = await res.json();
    console.log(`✅ [数据推送成功] 云端已接收 ${data.count} 条最新硬件行情！`);
    return true;
  } catch (err) {
    console.warn(`⚠️ [数据推送离线] 无法连接云端服务 (${err.message})，价格数据已妥善保留在本地。`);
    return false;
  }
}

if (require.main === module) {
  pushPricesToCloud();
}

module.exports = { pushPricesToCloud };
