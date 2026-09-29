const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const STATE_DIR = path.resolve(__dirname, '../state');
if (!fs.existsSync(STATE_DIR)) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
}

const PLATFORMS = {
  jd: {
    name: '京东',
    loginUrl: 'https://passport.jd.com/new/login.aspx',
    verifyMarkers: ['thor', 'pin', 'pinId'],
  },
  xianyu: {
    name: '闲鱼',
    loginUrl: 'https://www.goofish.com/',
    verifyMarkers: ['unb', '_nk_', 'tracknick'],
  },
  taobao: {
    name: '淘宝',
    loginUrl: 'https://login.taobao.com/member/login.jhtml',
    verifyMarkers: ['unb', 'tracknick', '_nk_'],
  },
};

async function loginPlatform(key) {
  const cfg = PLATFORMS[key];
  if (!cfg) {
    console.error(`未知平台: ${key}`);
    return false;
  }

  console.log(`\n======================================================`);
  console.log(`👉 正在打开真实浏览器窗口，请使用手机 App 扫码登录: [${cfg.name}]`);
  console.log(`   监听登录关键凭证: ${cfg.verifyMarkers.join(', ')}`);
  console.log(`======================================================\n`);

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    locale: 'zh-CN',
  });

  const page = await context.newPage();
  await page.goto(cfg.loginUrl, { waitUntil: 'domcontentloaded' });

  const timeoutMs = 300 * 1000; // 最多等待 5 分钟
  const startTime = Date.now();
  let success = false;

  while (Date.now() - startTime < timeoutMs) {
    try {
      const cookies = await context.cookies();
      const hit = cfg.verifyMarkers.filter(m => 
        cookies.some(c => c.name === m && c.value && c.value !== '0' && c.value !== 'null')
      );

      if (hit.length > 0) {
        console.log(`\n🎉 [${cfg.name}] 登录成功！检测到有效凭证: [${hit.join(', ')}]`);
        const stateFile = path.join(STATE_DIR, `${key}_state.json`);
        await context.storageState({ path: stateFile });
        console.log(`💾 登录状态已安全保存至: ${stateFile}`);
        success = true;
        break;
      }
    } catch (err) {
      console.warn(`读取 cookie 异常: ${err.message}`);
      break;
    }

    await page.waitForTimeout(2000);
  }

  await browser.close();
  return success;
}

async function main() {
  const target = process.argv[2] || 'all';
  const targets = target === 'all' ? Object.keys(PLATFORMS) : [target];

  console.log(`🚀 [本地电商扫码助手] 启动目标: ${targets.join(', ')}`);
  for (const t of targets) {
    await loginPlatform(t);
  }
  console.log(`\n✅ 登录流程完成！`);
}

if (require.main === module) {
  main().catch(err => {
    console.error('登录异常:', err);
    process.exit(1);
  });
}

module.exports = { PLATFORMS, STATE_DIR };
