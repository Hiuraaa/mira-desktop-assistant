// Browser integration against real Python stores and desktop chat lifecycle.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';

const require = createRequire(import.meta.url);
const playwright = require(process.env.MIRA_PLAYWRIGHT_MODULE || 'playwright');
const output = resolve(process.env.MIRA_PREVIEW_DIR || 'studio-preview');
await mkdir(output,{recursive:true});
const directory = await mkdtemp(join(tmpdir(),'mira-studio-ui-'));
const child = spawn(process.env.MIRA_TEST_PYTHON || 'python',['tests/studio_preview.py'],{
  env:{...process.env, PYTHONPATH:process.cwd(), MIRA_DATA_DIR:directory},stdio:['ignore','pipe','pipe']
});
let browser, errors = [], diagnostics = '';
child.stderr.on('data',chunk => { diagnostics += chunk.toString(); });
const url = await new Promise((resolveUrl,reject) => {
  let text = '';
  const timer = setTimeout(() => reject(new Error('Desktop preview did not start: '+diagnostics)),20000);
  child.stdout.on('data',chunk => {
    text += chunk.toString();
    if(text.includes('\n')) {clearTimeout(timer);try{resolveUrl(JSON.parse(text.split('\n')[0]).url);}catch(error){reject(error);}}
  });
  child.on('exit',code => {clearTimeout(timer);reject(new Error('Preview exited '+code+': '+diagnostics));});
});

try {
  browser = await playwright.chromium.launch(process.env.MIRA_BROWSER_EXECUTABLE
    ? {headless:true,executablePath:process.env.MIRA_BROWSER_EXECUTABLE}
    : {headless:true,channel:process.platform === 'win32' ? 'msedge' : undefined});
  const page = await browser.newPage({viewport:{width:1440,height:960},deviceScaleFactor:1});
  page.on('pageerror',error => errors.push(error.message));
  await page.goto(url);
  await page.locator('#startup').waitFor({state:'hidden'});
  await page.locator('#connection-title').getByText('Mira đã kết nối').waitFor();
  const noOverflow = async () => {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),'Horizontal overflow');
    const box = await page.locator('#send-btn').boundingBox();
    const viewport = page.viewportSize();
    assert(box && box.x >= 0 && box.x + box.width <= viewport.width && box.y+box.height <= viewport.height,'Send button outside viewport');
  };
  await noOverflow();
  await page.screenshot({path:join(output,'mira-studio-desktop.png')});

  await page.locator('#message-input').fill('Tôi thích trả lời tự nhiên, ngắn gọn.');
  await page.locator('#message-input').press('Enter');
  await page.locator('.assistant .message-content').getByText('Bạn có thể duyệt điều này',{exact:false}).waitFor();
  await page.locator('#send-btn').waitFor({state:'visible'});
  await page.waitForFunction(() => !document.querySelector('#send-btn').disabled);
  await page.locator('.primary-nav [data-view="memory"]').click();
  await page.locator('[data-candidate-accept]').click();
  await page.locator('#f-text').fill('Tôi thích câu trả lời tự nhiên và đủ ý.');
  await page.locator('#modal-save').click();
  await page.locator('#modal').waitFor({state:'hidden'});
  await page.locator('.memory-card:not(.candidate)').getByText('Tôi thích câu trả lời tự nhiên và đủ ý.',{exact:true}).waitFor();
  assert.equal(await page.locator('.candidate').count(),0);
  await page.screenshot({path:join(output,'mira-studio-memory.png')});

  await page.locator('.primary-nav [data-view="study"]').click();
  await page.locator('[data-action="source-add"]').click();
  await page.locator('#f-title').fill('Lịch làm việc');
  await page.locator('#f-text').fill('Dự án Cobalt họp vào 9 giờ sáng thứ Hai.');
  await page.locator('#modal-save').click();
  await page.locator('#modal').waitFor({state:'hidden'});
  await page.locator('.source-card').getByText('Lịch làm việc',{exact:true}).waitFor();
  await page.locator('[data-action="study-now"]').click();
  await page.waitForFunction(() => [...document.querySelectorAll('.source-card')].find(n => n.textContent.includes('Lịch làm việc'))?.textContent.includes('Sẵn sàng'));
  await page.locator('#auto-study').check();
  await page.locator('#study-interval').selectOption('15');
  await page.locator('.busy-banner h2').getByText('Tự ôn đang bật').waitFor();
  await page.screenshot({path:join(output,'mira-studio-study.png')});

  await page.locator('.primary-nav [data-view="chat"]').click();
  await page.locator('#message-input').fill('Cobalt dùng ngôn ngữ gì và cần sạc lúc nào?');
  await page.locator('#message-input').press('Enter');
  await page.locator('.assistant .message-content').getByText('Theo nguồn Dự án Cobalt',{exact:false}).waitFor();
  await page.waitForFunction(() => !document.querySelector('#send-btn').disabled);
  await page.screenshot({path:join(output,'mira-studio-chat.png')});
  await page.locator('[data-feedback]').last().click();
  await page.locator('#f-tags').fill('Cobalt, robot');
  await page.locator('#modal-save').click();
  await page.locator('#modal').waitFor({state:'hidden'});

  // Untrusted messages must remain text, with no scripts or image event handlers.
  await page.locator('#message-input').fill('<img src=x onerror="window.MIRA_XSS=true"><script>window.MIRA_XSS=true</script>');
  await page.locator('#message-input').press('Enter');
  await page.waitForFunction(() => !document.querySelector('#send-btn').disabled);
  assert.equal(await page.evaluate(() => window.MIRA_XSS),undefined);
  assert.equal(await page.locator('.message-content script,.message-content img').count(),0);

  // Reload keeps authenticated session and saved stores, and must not close the app.
  await page.reload();
  await page.locator('#startup').waitFor({state:'hidden'});
  await page.locator('.primary-nav [data-view="memory"]').click();
  await page.locator('.memory-card').getByText('Tôi thích câu trả lời tự nhiên và đủ ý.',{exact:true}).waitFor();
  await page.locator('[data-view="settings"].nav-item').click();
  await page.locator('#theme-choice').selectOption('dark');
  await page.locator('#settings-form button[type="submit"]').click();
  await page.waitForFunction(() => !document.querySelector('#settings-form button[type="submit"]').disabled);
  await page.waitForFunction(() => document.body.dataset.theme === 'dark');
  await page.locator('.primary-nav [data-view="chat"]').click();
  await page.screenshot({path:join(output,'mira-studio-dark.png')});
  await page.locator('[data-view="settings"].nav-item').click();
  await page.locator('#theme-choice').selectOption('light');
  await page.locator('#settings-form button[type="submit"]').click();
  await page.waitForFunction(() => !document.querySelector('#settings-form button[type="submit"]').disabled);
  await page.waitForFunction(() => document.body.dataset.theme === 'light');
  await page.locator('#new-chat').click();
  await page.locator('#view-chat.active #send-btn').waitFor({state:'visible'});

  for (const [width,height,name] of [[900,700,'laptop'],[430,850,'compact']]) {
    await page.setViewportSize({width,height});
    await noOverflow();
    await page.screenshot({path:join(output,`mira-studio-${name}.png`)});
    if(width < 670) {
      await page.locator('#menu-toggle').click();
      await page.locator('.primary-nav [data-view="study"]').click();
      await page.locator('#auto-study').waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
      await page.locator('#menu-toggle').click();
      await page.locator('.primary-nav [data-view="chat"]').click();
    }
  }
  assert.deepEqual(errors,[],'Browser exceptions');
  assert(!/Traceback|Exception in Tkinter callback/.test(diagnostics),diagnostics);
  console.log('Studio UI passed: desktop/laptop/compact layout, streaming chat, reviewed memory, source retrieval, feedback, session reload, themes and HTML escaping.');
} finally {
  if(browser) await browser.close();
  child.kill();
}
