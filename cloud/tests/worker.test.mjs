import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import worker, { deliverReminders } from '../worker.mjs';

const ACCESS_KEY = 'owner-generated-secret-at-least-24-chars';
const WEBHOOK_KEY = 'owner-telegram-webhook-secret';
const origin = 'https://mira-phone.example.workers.dev';

class D1 {
  constructor() {
    this.db = new DatabaseSync(':memory:');
    this.db.exec(readFileSync(new URL('../migrations/0001_init.sql', import.meta.url), 'utf8'));
  }
  prepare(sql) {
    const statement = this.db.prepare(sql);
    return {
      bind(...args) {
        return {
          first: async () => statement.get(...args) || null,
          all: async () => ({ results: statement.all(...args) }),
          run: async () => ({ meta: { changes: statement.run(...args).changes } }),
        };
      },
      first: async () => statement.get() || null,
      all: async () => ({ results: statement.all() }),
      run: async () => ({ meta: { changes: statement.run().changes } }),
    };
  }
  async batch(statements) {
    this.db.exec('BEGIN');
    try { for (const item of statements) await item.run(); this.db.exec('COMMIT'); }
    catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
}

function env() {
  const calls = [];
  return {
    calls, DB: new D1(), MIRA_ACCESS_KEY: ACCESS_KEY,
    MIRA_TIMEZONE: 'Asia/Ho_Chi_Minh',
    TELEGRAM_BOT_TOKEN: 'test-token', TELEGRAM_USER_ID: '123456789',
    TELEGRAM_WEBHOOK_SECRET: WEBHOOK_KEY,
    AI: { async run(model, body) {
      calls.push({ model, body });
      return { choices: [{ message: { content: 'Mira nghe đây. Mình giúp bạn nhé.' } }] };
    } },
    ASSETS: { fetch: async () => new Response('<html>login</html>', { headers: { 'Content-Type': 'text/html' } }) },
  };
}

function request(path, method = 'GET', data, key = ACCESS_KEY, extra = {}) {
  return new Request(origin + path, {
    method,
    headers: { 'X-Mira-Key': key, ...(data ? { 'Content-Type': 'application/json' } : {}), ...extra },
    body: data ? JSON.stringify(data) : undefined,
  });
}

async function call(environment, path, method = 'GET', data, key, extra) {
  const response = await worker.fetch(request(path, method, data, key, extra), environment);
  return { status: response.status, result: await response.json() };
}

test('API is private, cross-site writes fail, and setup cannot expose an empty secret', async () => {
  const cloud = env();
  assert.equal((await call(cloud, '/api/bootstrap', 'GET', undefined, 'invalid')).status, 401);
  assert.equal((await call(cloud, '/api/profile', 'PUT', { notes: 'leak' }, ACCESS_KEY, { Origin: 'https://bad.example' })).status, 403);
  assert.equal((await call(cloud, '/api/chat', 'POST', null)).status, 400);
  cloud.MIRA_ACCESS_KEY = '';
  assert.equal((await call(cloud, '/api/bootstrap')).status, 503);
  const staticPage = await worker.fetch(request('/'), cloud);
  assert.match(staticPage.headers.get('Content-Security-Policy'), /script-src 'self'/);
});

test('phone chat shares bounded history and uses preferences, does not pretend PC is accessible', async () => {
  const cloud = env();
  assert.equal((await call(cloud, '/api/profile', 'PUT', { notes: 'Tôi thích ví dụ về khoa học.' })).status, 200);
  const answer = await call(cloud, '/api/chat', 'POST', { text: 'Chào Mira' });
  assert.equal(answer.result.answer, 'Mira nghe đây. Mình giúp bạn nhé.');
  assert.equal(cloud.calls.length, 1);
  assert.equal(cloud.calls[0].model, '@cf/zai-org/glm-4.7-flash');
  assert.equal(cloud.calls[0].body.chat_template_kwargs.enable_thinking, false);
  assert.equal(cloud.calls[0].body.temperature, 0.3);
  assert.match(cloud.calls[0].body.messages[0].content, /đúng chính tả/);
  assert.match(cloud.calls[0].body.messages[0].content, /Không lặp lại lỗi viết/);
  assert.match(cloud.calls[0].body.messages[0].content, /Không thể xem pin/);
  assert.match(cloud.calls[0].body.messages[0].content, /khoa học/);
  const data = await call(cloud, '/api/bootstrap');
  assert.equal(data.result.messages.length, 2);
  assert.equal(data.result.messages[0].role, 'user');
  assert.equal(data.result.notes, 'Tôi thích ví dụ về khoa học.');
  await call(cloud, '/api/chat', 'POST', { text: 'Một câu khác' });
  assert.equal(cloud.calls.at(-1).body.messages.at(-3).content, 'Chào Mira');
  await call(cloud, '/api/history', 'DELETE');
  assert.equal((await call(cloud, '/api/bootstrap')).result.messages.length, 0);
});

test('reminder rejects past time; cron sends once only for owner; refused Telegram retries', async () => {
  const cloud = env();
  const past = await call(cloud, '/api/reminders', 'POST', { content: 'Quá khứ', dueAt: new Date(Date.now() - 60_000).toISOString() });
  assert.equal(past.status, 400);
  const due = new Date(Date.now() + 30_000);
  const future = await call(cloud, '/api/reminders', 'POST', { content: 'Uống nước', dueAt: due.toISOString() });
  assert.equal(future.status, 201);
  let sent = 0;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    sent++;
    assert.equal(JSON.parse(options.body).chat_id, cloud.TELEGRAM_USER_ID);
    assert.match(JSON.parse(options.body).text, /Uống nước/);
    return Response.json({ ok: true });
  };
  try {
    assert.equal(await deliverReminders(cloud, new Date(due.getTime() + 61_000)), 1);
    assert.equal(await deliverReminders(cloud, new Date(due.getTime() + 122_000)), 0);
    assert.equal(sent, 1);
  } finally { globalThis.fetch = realFetch; }
  assert.equal((await call(cloud, '/api/bootstrap')).result.reminders.length, 0);
});

test('webhook requires shared secret and owner ID; repeated update does not run AI twice', async () => {
  const cloud = env();
  const message = { update_id: 42, message: { text: 'Chào Mira', from: { id: 123456789 }, chat: { id: 123456789, type: 'private' } } };
  const realFetch = globalThis.fetch;
  const sent = [];
  globalThis.fetch = async (_url, options) => { sent.push(JSON.parse(options.body)); return Response.json({ ok: true }); };
  try {
    assert.equal((await call(cloud, '/telegram', 'POST', message)).status, 403);
    message.message.from.id = 999;
    assert.equal((await call(cloud, '/telegram', 'POST', message, ACCESS_KEY, { 'X-Telegram-Bot-Api-Secret-Token': WEBHOOK_KEY })).status, 200);
    assert.equal(cloud.calls.length, 0);
    message.message.from.id = 123456789;
    assert.equal((await call(cloud, '/telegram', 'POST', message, ACCESS_KEY, { 'X-Telegram-Bot-Api-Secret-Token': WEBHOOK_KEY })).status, 200);
    assert.equal((await call(cloud, '/telegram', 'POST', message, ACCESS_KEY, { 'X-Telegram-Bot-Api-Secret-Token': WEBHOOK_KEY })).status, 200);
    assert.equal(cloud.calls.length, 1);
    assert.equal(sent.length, 1);
    assert.equal(sent[0].chat_id, '123456789');
  } finally { globalThis.fetch = realFetch; }
});

test('Telegram /nhac works off laptop and failed reminder delivery can retry', async () => {
  const cloud = env();
  const realFetch = globalThis.fetch;
  let fail = false;
  const sent = [];
  globalThis.fetch = async (_url, options) => {
    if (fail) return Response.json({ ok: false }, { status: 503 });
    sent.push(JSON.parse(options.body).text);
    return Response.json({ ok: true });
  };
  try {
    const update = { update_id: 73, message: { text: '/nhac 2p | Đứng dậy', from: { id: 123456789 }, chat: { id: 123456789, type: 'private' } } };
    assert.equal((await call(cloud, '/telegram', 'POST', update, ACCESS_KEY, { 'X-Telegram-Bot-Api-Secret-Token': WEBHOOK_KEY })).status, 200);
    assert.match(sent[0], /Đã ghi lịch/);
    const reminders = (await call(cloud, '/api/bootstrap')).result.reminders;
    assert.equal(reminders.length, 1);
    fail = true;
    assert.equal(await deliverReminders(cloud, new Date(Date.now() + 3 * 60_000)), 0);
    assert.equal((await call(cloud, '/api/bootstrap')).result.reminders[0].state, 'pending');
    fail = false;
    assert.equal(await deliverReminders(cloud, new Date(Date.now() + 4 * 60_000)), 1);
    assert.match(sent[1], /Đứng dậy/);
  } finally { globalThis.fetch = realFetch; }
});

test('AI quota does not save a phantom answer and time request works without AI', async () => {
  const cloud = env();
  cloud.AI.run = async () => { throw new Error('account limited: 3036'); };
  const quota = await call(cloud, '/api/chat', 'POST', { text: 'Tôi hỏi một câu' });
  assert.equal(quota.status, 503);
  assert.match(quota.result.error, /miễn phí/);
  assert.equal((await call(cloud, '/api/bootstrap')).result.messages.length, 0);
  const time = await call(cloud, '/api/chat', 'POST', { text: 'Mấy giờ rồi?' });
  assert.equal(time.status, 200);
  assert.match(time.result.answer, /Asia\/Ho_Chi_Minh/);
});
