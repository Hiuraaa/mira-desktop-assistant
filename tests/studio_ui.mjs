// Browser integration against real Python stores and desktop chat lifecycle.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
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
    await page.waitForFunction(() => innerWidth >= 670 || document.querySelector('.sidebar').getBoundingClientRect().right <= 1);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),'Horizontal overflow');
    const box = await page.locator('#send-btn').boundingBox();
    const viewport = page.viewportSize();
    assert(box && box.x >= 0 && box.x + box.width <= viewport.width && box.y+box.height <= viewport.height,'Send button outside viewport');
  };
  const capture = async name => {
    await page.waitForFunction(() => !document.querySelector('#toasts .toast'));
    await page.screenshot({path:join(output,`mira-studio-${name}.png`),animations:'disabled'});
  };
  await noOverflow();
  await capture('desktop');

  // Verify the real UI switch, backend setting and reply completion agree.
  // The fixture records TTS requests and never plays sound or opens Win+H.
  const audio = async () => JSON.parse(await readFile(join(directory,'test-audio.json'),'utf8'));
  const settings = async () => JSON.parse(await readFile(join(directory,'settings.json'),'utf8'));
  const settingsView = () => page.locator('[data-view="settings"].nav-item').click();
  const chatView = () => page.locator('.primary-nav [data-view="chat"]').click();
  const voiceSwitch = page.locator('#settings-form input[name="voice_auto"]');
  const voiceSaved = async enabled => {
    await page.waitForFunction(() => !document.querySelector('#settings-form input[name="voice_auto"]').disabled);
    await page.waitForFunction(async expected => {
      const state = await (await fetch('/api/state',{cache:'no-store'})).json();
      return state.config.voice_auto === expected;
    },enabled);
    assert.equal((await settings()).voice_auto,enabled);
  };
  const replyDone = () => page.waitForFunction(() => !document.querySelector('#send-btn').disabled);
  await page.locator('#dictate').click();
  await page.locator('#message-input').fill('Chào Mira, mình vừa dùng mic.');
  await page.locator('#message-input').press('Enter');
  await replyDone();
  assert.equal((await audio()).dictations,1);
  assert.equal((await audio()).calls.length,0,'Dictation bypassed the muted voice setting');

  await settingsView();
  await page.locator('[name="persona_note"]').fill('Bản nháp phải được giữ khi đổi giọng đọc.');
  await voiceSwitch.check();
  await voiceSaved(true);
  assert.equal(await page.locator('[name="persona_note"]').inputValue(),'Bản nháp phải được giữ khi đổi giọng đọc.');
  assert.equal((await settings()).persona_note,'','Voice switch saved an unrelated settings draft');
  await chatView();
  await page.locator('#message-input').fill('Giờ hãy trả lời bằng giọng đã bật.');
  await page.locator('#message-input').press('Enter');
  await replyDone();
  assert.equal((await audio()).calls.length,1);
  assert.equal((await audio()).active,true);
  await settingsView();
  await voiceSwitch.uncheck();
  await voiceSaved(false);
  assert.equal((await audio()).active,false,'Muting did not stop the active playback');

  await voiceSwitch.check();
  await voiceSaved(true);
  await chatView();
  await page.locator('#message-input').fill('Kiểm tra giọng đọc khi đang chờ.');
  await page.locator('#message-input').press('Enter');
  await page.waitForFunction(() => document.querySelector('#send-btn').disabled);
  await settingsView();
  await voiceSwitch.uncheck();
  await voiceSaved(false);
  await writeFile(join(directory,'release-voice-test'),'continue');
  await replyDone();
  assert.equal((await audio()).calls.length,1,'A pending reply spoke after the user muted it');
  await page.reload();
  await page.locator('#startup').waitFor({state:'hidden'});
  await settingsView();
  assert.equal(await voiceSwitch.isChecked(),false,'Reload showed a different voice setting');
  await chatView();
  const listenOnce = async () => {
    await Promise.all([
      page.waitForResponse(response => response.url().endsWith('/api/command') &&
        response.request().postDataJSON()?.data?.name === 'listen' && response.ok()),
      page.locator('[data-tool="listen"]').last().click()
    ]);
  };
  await listenOnce();
  assert.equal((await audio()).calls.length,2,'Explicit manual Listen stopped working');
  await listenOnce();
  assert.equal((await audio()).active,false);
  await page.locator('#new-chat').click();

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
  await capture('memory');

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
  await capture('study');

  await page.locator('.primary-nav [data-view="chat"]').click();
  await page.locator('#message-input').fill('Cobalt dùng ngôn ngữ gì và cần sạc lúc nào?');
  await page.locator('#message-input').press('Enter');
  await page.locator('.assistant .message-content').getByText('Theo nguồn Dự án Cobalt',{exact:false}).waitFor();
  await page.waitForFunction(() => !document.querySelector('#send-btn').disabled);
  await capture('chat');
  await page.locator('[data-feedback]').last().click();
  await page.locator('#f-tags').fill('Cobalt, robot');
  await page.locator('#modal-save').click();
  await page.locator('#modal').waitFor({state:'hidden'});

  // Untrusted messages must remain text, with no scripts or image event handlers.
  await page.locator('#message-input').fill('<img src=x onerror="window.MIRA_XSS=true"><script>window.MIRA_XSS=true</script>');
  await page.locator('#message-input').press('Enter');
  await page.locator('.user .message-content').getByText('<img src=x onerror="window.MIRA_XSS=true"><script>window.MIRA_XSS=true</script>',{exact:true}).waitFor();
  await page.locator('.assistant .message-content').getByText('Bạn đang muốn ưu tiên điều gì?',{exact:true}).waitFor();
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
  await page.locator('#view-chat.active .assistant .message-content').getByText('Theo nguồn Dự án Cobalt',{exact:false}).waitFor();
  await noOverflow();
  await capture('dark');
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
    await capture(name);
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
  console.log('Studio UI passed: voice switch saves immediately, dictation respects mute, active/pending speech stops, reload and manual Listen; desktop/laptop/compact layout, streaming chat, reviewed memory, source retrieval, feedback, themes and HTML escaping.');
} finally {
  if(browser) await browser.close();
  child.kill();
}
