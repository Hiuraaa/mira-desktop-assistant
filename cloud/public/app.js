const $ = (id) => document.getElementById(id);
const state = { key: sessionStorage.getItem('miraAccessKey') || '', messages: [], reminders: [], telegram: false, busy: false };

async function api(path, method = 'GET', data) {
  const response = await fetch(path, {
    method,
    headers: { 'X-Mira-Key': state.key, ...(data ? { 'Content-Type': 'application/json' } : {}) },
    body: data ? JSON.stringify(data) : undefined,
    cache: 'no-store',
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('Không đọc được phản hồi từ Mira.'); }
  if (!response.ok) {
    if (response.status === 401) { sessionStorage.removeItem('miraAccessKey'); $('app').hidden = true; $('login').hidden = false; }
    throw new Error(result.error || 'Mira đang bận. Bạn thử lại nhé.');
  }
  return result;
}

function setStatus(id, message) { $(id).textContent = message || ''; }
function timeLabel(instant) {
  try { return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(instant)); }
  catch { return ''; }
}
function el(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function renderAssistantText(container, text) {
  const lines = text.split('\n');
  lines.forEach((line, index) => {
    // Render only simple emphasis and list markers. All model text remains text nodes.
    const readable = line.replace(/^\s*[-*]\s+(?=\S)/, '• ');
    let offset = 0;
    for (const match of readable.matchAll(/\*\*([^*\n]+)\*\*/g)) {
      container.append(document.createTextNode(readable.slice(offset, match.index)));
      container.append(el('strong', '', match[1]));
      offset = match.index + match[0].length;
    }
    container.append(document.createTextNode(readable.slice(offset)));
    if (index < lines.length - 1) container.append(document.createTextNode('\n'));
  });
}

function renderMessages() {
  const box = $('conversation');
  box.replaceChildren();
  if (!state.messages.length) {
    const welcome = el('div', 'welcome');
    welcome.append(el('strong', '', 'Mira luôn sẵn sàng ✦'), el('span', '', 'Hôm nay có chuyện gì bạn muốn kể, hay cần mình nhắc điều gì?'));
    box.append(welcome);
  }
  for (const message of state.messages) {
    const row = el('article', `bubble ${message.role}`);
    const who = el('div', 'who', message.role === 'user' ? 'Bạn' : 'Mira');
    const content = el('div', 'bubble-text');
    if (message.role === 'assistant') renderAssistantText(content, message.content);
    else content.textContent = message.content;
    const when = el('time', 'time', timeLabel(message.created_at));
    row.append(who, content, when);
    box.append(row);
  }
}

function renderReminders() {
  const box = $('reminder-list');
  box.replaceChildren();
  const items = state.reminders.filter(item => item.state === 'pending' || item.state === 'sending');
  $('reminder-count').textContent = `${items.length} lịch đang chờ`;
  if (!items.length) { box.append(el('div', 'empty', 'Chưa có lịch nào. Thêm một điều bạn muốn Mira nhớ giúp nhé.')); return; }
  for (const item of items.sort((a, b) => a.due_at.localeCompare(b.due_at))) {
    const card = el('div', 'reminder');
    const content = el('div');
    const due = el('time', '', timeLabel(item.due_at));
    due.dateTime = item.due_at;
    content.append(el('strong', '', item.content), due);
    const remove = el('button', '', 'Xóa');
    remove.type = 'button';
    remove.setAttribute('aria-label', `Xóa lịch ${item.content}`);
    remove.addEventListener('click', async () => {
      remove.disabled = true;
      try {
        const result = await api(`/api/reminders/${encodeURIComponent(item.id)}`, 'DELETE');
        if (!result.deleted) throw new Error('Lịch đã đến giờ gửi hoặc đã được xóa.');
        state.reminders = state.reminders.filter(entry => entry.id !== item.id);
        renderReminders();
      } catch (err) { setStatus('reminder-status', err.message); remove.disabled = false; }
    });
    card.append(content, remove);
    box.append(card);
  }
}

function showTab(tab) {
  for (const panel of document.querySelectorAll('.panel')) {
    panel.hidden = panel.id !== tab;
    panel.classList.toggle('active', panel.id === tab);
  }
  for (const item of document.querySelectorAll('.nav-item')) {
    item.classList.toggle('active', item.dataset.tab === tab);
    if (item.dataset.tab === tab) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  }
  window.scrollTo({ top: 0, behavior: 'auto' });
}

async function openMira() {
  const [session, data] = await Promise.all([api('/api/session'), api('/api/bootstrap')]);
  state.telegram = session.telegram;
  state.messages = data.messages;
  state.reminders = data.reminders;
  $('notes').value = data.notes;
  $('note-count').textContent = `${data.notes.length} / 1600`;
  $('cloud-state').textContent = 'Mira đang online';
  $('telegram-hint').textContent = state.telegram
    ? 'Đã kết nối Telegram. Mira sẽ gửi nhắc lịch qua bot khi đến giờ (có thể chậm khoảng một phút).'
    : 'Bạn chưa nối bot Telegram: lịch được lưu nhưng điện thoại sẽ không nhận thông báo khi đóng trang. Xem cloud/README.md để bật nhắc qua Telegram.';
  $('login').hidden = true;
  $('app').hidden = false;
  $('login-error').textContent = '';
  renderMessages();
  renderReminders();
  showTab('chat');
}

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  state.key = $('access-key').value;
  try { await openMira(); sessionStorage.setItem('miraAccessKey', state.key); $('access-key').value = ''; }
  catch (err) { $('login-error').textContent = err.message; state.key = ''; }
  finally { button.disabled = false; }
});

$('chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = $('message').value.trim();
  if (!text || state.busy) return;
  state.busy = true;
  $('send').disabled = true;
  setStatus('chat-status', 'Mira đang nghĩ…');
  state.messages.push({ role: 'user', content: text, created_at: new Date().toISOString() });
  renderMessages();
  $('message').value = '';
  $('conversation').lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  try {
    const response = await api('/api/chat', 'POST', { text });
    state.messages.push({ role: 'assistant', content: response.answer, created_at: new Date().toISOString() });
    $('conversation').lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' });
    setStatus('chat-status', '');
  } catch (err) {
    state.messages.pop();
    $('message').value = text;
    setStatus('chat-status', err.message);
  } finally {
    state.busy = false; $('send').disabled = false; renderMessages();
    $('conversation').lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }
});
$('message').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); }
});

$('clear-chat').addEventListener('click', async () => {
  if (!confirm('Xóa toàn bộ lịch sử chat trên Mira cloud, kể cả tin nhắn từ Telegram?')) return;
  try { await api('/api/history', 'DELETE'); state.messages = []; renderMessages(); setStatus('chat-status', 'Đã xóa lịch sử chat trên cloud.'); }
  catch (err) { setStatus('chat-status', err.message); }
});

$('reminder-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const due = new Date($('reminder-time').value);
  if (!Number.isFinite(due.getTime()) || due.getTime() < Date.now() + 10000) { setStatus('reminder-status', 'Hãy chọn một thời gian trong tương lai.'); return; }
  $('add-reminder').disabled = true;
  try {
    const item = await api('/api/reminders', 'POST', { content: $('reminder-text').value, dueAt: due.toISOString() });
    state.reminders.push({ ...item, due_at: item.dueAt });
    renderReminders();
    event.currentTarget.reset();
    setStatus('reminder-status', 'Đã lưu lịch.');
  } catch (err) { setStatus('reminder-status', err.message); }
  finally { $('add-reminder').disabled = false; }
});

$('notes').addEventListener('input', () => { $('note-count').textContent = `${$('notes').value.length} / 1600`; });
$('memory-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await api('/api/profile', 'PUT', { notes: $('notes').value }); setStatus('memory-status', 'Đã lưu ghi chú cho Mira.'); }
  catch (err) { setStatus('memory-status', err.message); }
});

function configureComputerLink() {
  const link = $('computer-link');
  const address = $('computer-url').value.trim();
  try {
    const target = new URL(address);
    if (target.protocol !== 'https:' || !target.hostname.endsWith('.ts.net')) throw new Error();
    localStorage.setItem('miraPcUrl', target.href);
    link.href = target.href;
    link.classList.remove('disabled-link');
    setStatus('computer-status', '');
  } catch {
    link.href = '#'; link.classList.add('disabled-link');
    localStorage.removeItem('miraPcUrl');
    setStatus('computer-status', address ? 'Hãy nhập địa chỉ HTTPS của máy trên Tailscale (*.ts.net).' : '');
  }
}
$('computer-url').value = localStorage.getItem('miraPcUrl') || '';
$('computer-url').addEventListener('change', configureComputerLink);
if ($('computer-url').value) configureComputerLink();

$('logout').addEventListener('click', () => {
  sessionStorage.removeItem('miraAccessKey'); state.key = ''; state.messages = []; state.reminders = [];
  $('app').hidden = true; $('login').hidden = false; $('access-key').focus();
});
for (const button of document.querySelectorAll('.nav-item')) button.addEventListener('click', () => showTab(button.dataset.tab));
if (state.key) openMira().catch(err => { $('login-error').textContent = err.message; state.key = ''; sessionStorage.removeItem('miraAccessKey'); });
