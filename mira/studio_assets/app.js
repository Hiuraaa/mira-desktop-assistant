"use strict";

const $ = (selector, parent = document) => parent.querySelector(selector);
const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const titles = {chat:"Trò chuyện", memory:"Bộ nhớ", study:"Học tập", tools:"Công cụ", settings:"Cài đặt"};
let state = null, csrf = "", view = "chat", polling = false, sending = false;
let feedSignature = "", memorySignature = "", studySignature = "", toolsSignature = "";
let modalSubmit = null, stopped = false, lastPoll = 0, lastActivity = 0;
const drafts = new Map();

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = "toast" + (error ? " error" : "");
  node.innerHTML = icon(error ? "close" : "check") + `<span>${esc(message)}</span>`;
  $("#toasts").append(node);
  setTimeout(() => node.remove(), error ? 8000 : 4500);
}

async function request(path, body) {
  const response = await fetch(path, body === undefined ? {cache:"no-store"} : {
    method:"POST", headers:{"Content-Type":"application/json", "X-Mira-CSRF":csrf},
    body:JSON.stringify(body), cache:"no-store"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Không kết nối được Mira.");
  return data;
}

async function command(operation, data = {}) {
  const result = await request("/api/command", {operation, data});
  await poll();
  return result;
}

function openModal({title, body, saveLabel = "Lưu", onSave, eyebrow = "MIRA STUDIO"}) {
  const dialog = $("#modal");
  if (dialog.open) dialog.close();
  $("#modal-title").textContent = title;
  $("#modal-eyebrow").textContent = eyebrow;
  $("#modal-body").innerHTML = body;
  $("#modal-save").textContent = saveLabel;
  $("#modal-save").disabled = false;
  modalSubmit = onSave;
  dialog.showModal();
  setTimeout(() => $("input,textarea,select", $("#modal-body"))?.focus(), 50);
}

function field(label, name, value = "", maximum = 500, rows = 0, note = "") {
  return `<div class="field"><label for="f-${name}">${esc(label)}</label>${rows
    ? `<textarea id="f-${name}" name="${name}" rows="${rows}" maxlength="${maximum}" required>${esc(value)}</textarea>`
    : `<input id="f-${name}" name="${name}" maxlength="${maximum}" value="${esc(value)}" required>`}
    ${note ? `<small>${esc(note)}</small>` : ""}</div>`;
}

function confirmAction(title, note, operation, data) {
  openModal({title, body:`<p class="modal-intro">${esc(note)}</p>`, saveLabel:"Xác nhận",
    onSave:() => command(operation, data)});
}

function empty(title, description, name = "memory") {
  return `<div class="empty-state"><span class="tile-icon">${icon(name)}</span><strong>${esc(title)}</strong><p>${esc(description)}</p></div>`;
}

function markdown(text) {
  // Escape raw HTML first. Only local formatting and http(s) links are introduced.
  const blocks = [];
  let safe = esc(text).replace(/[\uE000\uE001]/g, "");
  safe = safe.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, content) => {
    blocks.push(`<pre><code>${content}</code></pre>`);
    return `\n\n\uE000${blocks.length - 1}\uE001\n\n`;
  });
  const inline = line => line.replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  const groups = safe.split(/\n\s*\n/).filter(Boolean);
  return groups.map(group => {
    if (/^\uE000\d+\uE001$/.test(group.trim())) return group.trim();
    const lines = group.split("\n");
    if (lines.every(line => /^\s*[-*] /.test(line))) return "<ul>" + lines.map(line => `<li>${inline(line.replace(/^\s*[-*] /,""))}</li>`).join("") + "</ul>";
    if (lines.every(line => /^\s*\d+[.)] /.test(line))) return "<ol>" + lines.map(line => `<li>${inline(line.replace(/^\s*\d+[.)] /,""))}</li>`).join("") + "</ol>";
    if (lines.length === 1 && /^#{1,4} /.test(group)) return `<h3>${inline(group.replace(/^#{1,4} /,""))}</h3>`;
    if (lines.every(line => /^&gt; /.test(line))) return `<blockquote>${lines.map(line => inline(line.slice(5))).join("<br>")}</blockquote>`;
    return `<p>${lines.map(inline).join("<br>")}</p>`;
  }).join("").replace(/\uE000(\d+)\uE001/g, (_, index) => blocks[Number(index)] || "");
}

function welcome() {
  return `<div class="welcome"><div class="welcome-kicker">${icon("star")}MỘT CHÚT CẢM HỨNG CHO HÔM NAY</div><h2>Một ngày mới,<br>cùng <em>${esc(state.name)}.</em></h2><p class="welcome-description">Một người bạn để trò chuyện, một trợ lý để cùng làm việc.<br>Bạn muốn bắt đầu từ đâu hôm nay?</p><div class="welcome-label">THỬ MỘT ĐIỀU NHỎ</div><div class="suggestion-grid">
    <button class="suggestion" data-prompt="Giúp tôi lên một kế hoạch nhẹ nhàng cho hôm nay. Hỏi tôi việc quan trọng trước nhé."><span class="tile-icon sage">${icon("clock")}</span><strong>Lên kế hoạch hôm nay</strong><small>Cùng chia việc cho dễ bắt đầu</small>${icon("arrow")}</button>
    <button class="suggestion" data-prompt="Hôm nay tôi muốn tâm sự một chút. Hãy trò chuyện ngắn gọn, tự nhiên với tôi nhé."><span class="tile-icon rose">${icon("heart")}</span><strong>Kể Mira nghe</strong><small>Một câu chuyện, một ý tưởng</small>${icon("arrow")}</button>
    <button class="suggestion" data-view="study"><span class="tile-icon">${icon("book")}</span><strong>Dạy Mira điều mới</strong><small>Thêm tài liệu bạn muốn Mira biết</small>${icon("arrow")}</button>
  </div></div>`;
}

function renderFeed() {
  const signature = JSON.stringify([state.chat_id,state.messages,state.busy,state.stream,state.error]);
  if (signature === feedSignature) return;
  const feed = $("#chat-feed");
  const previousChat = feed.dataset.chat;
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 95;
  const oldPosition = feed.scrollTop;
  feed.dataset.chat = state.chat_id;
  feedSignature = signature;
  let html = state.messages.length ? "" : welcome();
  for (const [index, message] of state.messages.entries()) {
    if (message.role === "user") {
      html += `<article class="message user"><div class="message-content">${esc(message.content)}</div></article>`;
    } else {
      html += `<article class="message assistant"><div class="message-name"><span class="message-mark">✦</span>${esc(state.name)}</div><div class="message-content">${markdown(message.content)}</div><div class="message-actions"><button class="icon-btn" data-copy="${index}" title="Sao chép" aria-label="Sao chép câu trả lời">${icon("copy")}</button><button class="icon-btn" data-tool="listen" title="Nghe câu trả lời mới nhất" aria-label="Nghe câu trả lời mới nhất">${icon("volume")}</button><button class="icon-btn" data-feedback="${index}" title="Dạy Mira cách trả lời bạn thích" aria-label="Dạy Mira cách trả lời bạn thích">${icon("heart")}</button><button class="text-btn" data-feedback="${index}">Dạy cách trả lời</button></div></article>`;
    }
  }
  if (state.busy) {
    if (!state.messages.length) html = "";
    html += `<article class="message assistant" aria-label="Mira đang trả lời"><div class="message-name"><span class="message-mark">✦</span>${esc(state.name)}<span class="thinking-label">${state.stream ? "đang trả lời" : "đang nghĩ…"}</span></div><div class="message-content">${state.stream ? markdown(state.stream) : '<span class="thinking-dots"><i></i><i></i><i></i></span>'}</div></article>`;
  }
  if (state.error) html += `<div class="error-box">${esc(state.error)}</div>`;
  feed.innerHTML = html;
  if (previousChat !== state.chat_id || nearBottom || state.messages.length < 2) feed.scrollTop = feed.scrollHeight;
  else feed.scrollTop = oldPosition;
}

function renderSidebar() {
  const search = $("#history-search").value.toLocaleLowerCase("vi");
  const chats = state.chats.filter(chat => chat.title.toLocaleLowerCase("vi").includes(search));
  const signature = JSON.stringify([chats,state.chat_id]);
  const list = $("#history-list");
  if (list.dataset.signature !== signature) {
    list.dataset.signature = signature;
    list.innerHTML = chats.length ? chats.map(chat => `<div class="history-item${chat.id === state.chat_id ? " selected" : ""}"><button class="history-title" data-chat="${esc(chat.id)}" title="${esc(chat.title)}">${esc(chat.title)}</button><button class="icon-btn" data-chat-options="${esc(chat.id)}" aria-label="Tùy chọn ${esc(chat.title)}">${icon("more")}</button></div>`).join("") : '<p class="history-empty">Chưa có cuộc trò chuyện phù hợp.</p>';
  }
  const candidates = state.learning.candidates.length;
  $("#memory-badge").hidden = !candidates;
  $("#memory-badge").textContent = candidates;
  $("#study-dot").hidden = !state.learning.auto;
  const connected = !/chưa|không|lỗi|đang kiểm tra/i.test(state.health) && /sẵn sàng|Cloud/i.test(state.health);
  $("#connection-title").textContent = connected ? "Mira đã kết nối" : "Kiểm tra mô hình";
  $("#connection-model").textContent = state.config.model;
  $("#connection-model").title = state.health;
  $("#connection-dot").classList.toggle("offline", /chưa có|không|lỗi/i.test(state.health));
}

function renderCompanion() {
  $("#companion-name").textContent = state.name;
  $("#companion-state").textContent = state.busy ? "Mình đang nghĩ về điều bạn vừa nói." : "Mình đang ở đây, cứ nhắn nhé.";
  $("#presence-text").textContent = state.busy ? "Đang trả lời bạn" : "Sẵn sàng lắng nghe";
  $("#avatar-stage").classList.toggle("thinking", state.busy);
  const image = $("#mira-avatar");
  const source = state.avatar_custom ? "/api/avatar?v=" + state.avatar_revision : "/mira.svg?style=" + encodeURIComponent(state.avatar_style);
  if (image.getAttribute("src") !== source) image.src = source;
  const signature = JSON.stringify(state.memories.slice(-3));
  if ($("#memory-preview").dataset.signature !== signature) {
    $("#memory-preview").dataset.signature = signature;
    $("#memory-preview").innerHTML = state.memories.length ? state.memories.slice(-3).reverse().map(memory => `<div class="memory-note">${icon("memory")}<span>${esc(memory.text.slice(0,120))}${memory.text.length > 120 ? "…" : ""}</span></div>`).join("") : '<div class="empty-memory">Dạy mình một điều nhé.<br>Ví dụ: “Tôi thích câu trả lời ngắn.”</div>';
  }
  const queued = state.learning.sources.filter(source => source.status === "queued").length;
  $("#study-preview").textContent = state.learning.auto ? `Tự ôn đang bật · ${queued} nguồn chờ` : "Để Mira chuẩn bị tài liệu";
}

function stat(number, label, name, color = "") {
  return `<div class="stat-card"><span class="tile-icon ${color}">${icon(name)}</span><div><strong>${number}</strong><span>${esc(label)}</span></div></div>`;
}

function renderMemory(force = false) {
  const signature = JSON.stringify([state.memories,state.preferences,state.learning.candidates]);
  if (!force && signature === memorySignature) return;
  memorySignature = signature;
  const memories = state.memories, candidates = state.learning.candidates, preferences = state.preferences;
  $("#view-memory").innerHTML = `<div class="page-content"><div class="page-heading"><div><span class="eyebrow">HIỂU BẠN THÊM MỖI NGÀY</span><h1>Những điều Mira nhớ.</h1><p>Bộ nhớ và cách trả lời do bạn chọn. Các điều Mira nhận ra trong lúc chat sẽ chờ bạn duyệt trước khi được lưu lâu dài.</p></div><div class="heading-actions"><button class="btn primary" data-action="memory-add">${icon("plus")}Thêm điều cần nhớ</button></div></div>
    <div class="stats-row">${stat(memories.length,"Ký ức đã lưu","memory")}${stat(candidates.length,"Gợi ý chờ bạn duyệt","edit","peach")}${stat(preferences.examples.length,"Ví dụ cách trả lời","heart","rose")}</div>
    ${candidates.length ? `<div class="section-heading"><h2>Chờ bạn xem lại <span class="count">${candidates.length}</span></h2><p>Lấy từ lời bạn nói với Mira</p></div><div class="memory-grid">${candidates.map(c => `<article class="memory-card candidate"><div class="memory-meta"><span>GỢI Ý BỘ NHỚ</span>${icon("edit")}</div><p>${esc(c.text)}</p><div class="memory-controls"><button class="btn secondary" data-candidate-ignore="${esc(c.id)}">Bỏ qua</button><button class="btn primary" data-candidate-accept="${esc(c.id)}">Xem & lưu</button></div></article>`).join("")}</div>` : ""}
    <div class="section-heading"><h2>Bộ nhớ của bạn <span class="count">${memories.length}/50</span></h2></div>${memories.length ? `<div class="memory-grid">${[...memories].reverse().map(m => `<article class="memory-card"><div class="memory-meta"><span>ĐÃ ĐƯỢC BẠN LƯU</span>${icon("memory")}</div><p>${esc(m.text)}</p><div class="memory-controls"><button class="icon-btn" data-memory-edit="${esc(m.id)}" aria-label="Sửa ký ức">${icon("edit")}</button><button class="icon-btn" data-memory-delete="${esc(m.id)}" aria-label="Xóa ký ức">${icon("trash")}</button></div></article>`).join("")}</div>` : empty("Bắt đầu từ một điều nhỏ",'Nhấn “Thêm điều cần nhớ”, hoặc nhắn “Tôi thích…” / “Nhớ rằng…” trong chat. Bạn có thể sửa hoặc xóa bất cứ lúc nào.')}
    <div class="split-sections"><section><div class="section-heading"><h2>Cách mình trò chuyện</h2><button class="text-btn" data-action="rule-add">+ Thêm quy tắc</button></div><div class="rule-list">${preferences.rules.map(r => `<div class="rule-item"><span class="tile-icon">${icon("chat")}</span><p>${esc(r.text)}</p><button class="icon-btn" data-preference-delete="${esc(r.id)}" aria-label="Xóa quy tắc">${icon("trash")}</button></div>`).join("") || empty("Bạn thích Mira nói thế nào?","Thêm một quy tắc về giọng điệu hoặc độ dài câu trả lời.","chat")}</div></section><section><div class="section-heading"><h2>Những câu trả lời bạn thích</h2><button class="text-btn" data-action="example-add">+ Dạy một ví dụ</button></div><div class="rule-list">${preferences.examples.map(e => `<div class="rule-item example-item"><div><strong>${esc(e.request)}</strong><p class="example-answer">${esc(e.ideal_answer)}</p></div><button class="icon-btn" data-preference-delete="${esc(e.id)}" aria-label="Xóa ví dụ">${icon("trash")}</button></div>`).join("") || empty("Dạy Mira bằng ví dụ",'Chọn biểu tượng trái tim dưới câu trả lời, rồi sửa thành cách bạn muốn Mira diễn đạt.',"heart")}</div></section></div>
    <div class="info-note">${icon("shield")}<span>Bộ nhớ được lưu trên máy này. Khi bạn dùng mô hình cloud, các ký ức và tài liệu liên quan có thể được gửi kèm câu hỏi sau khi bạn đồng ý dùng cloud. Mira không tự thay đổi trọng số mô hình.</span></div><button class="text-btn" data-tool="memories_advanced">Mở nhập/xuất bộ nhớ và đồng bộ điện thoại</button></div>`;
}

function renderStudy(force = false) {
  const signature = JSON.stringify(state.learning);
  if (!force && signature === studySignature) return;
  studySignature = signature;
  const learning = state.learning, sources = learning.sources;
  const ready = sources.filter(source => source.status === "ready").length;
  $("#view-study").innerHTML = `<div class="page-content"><div class="page-heading"><div><span class="eyebrow">HỌC TỪ NHỮNG ĐIỀU BẠN CHỌN</span><h1>Để Mira chuẩn bị,<br>khi bạn đang bận.</h1><p>Thêm ghi chú, kiến thức hoặc tài liệu của bạn. Mira sẽ sắp xếp chúng để tra lại khi bạn hỏi, rồi để lại báo cáo cho bạn xem sau.</p></div><div class="heading-actions"><button class="btn secondary" data-action="source-import">${icon("file")}Nhập .txt / .md</button><button class="btn primary" data-action="source-add">${icon("plus")}Thêm tài liệu</button></div></div>
    <div class="busy-banner"><span class="tile-icon">${icon("book")}</span><div><h2>${learning.auto ? "Tự ôn đang bật" : "Bật tự ôn khi bạn rảnh tay"}</h2><p>Chỉ xử lý tài liệu bạn thêm, khi bạn ngừng tương tác ít nhất 1 phút và Mira không trả lời. Hãy giữ app mở và laptop không ngủ.</p></div><div class="busy-controls"><label class="toggle"><input type="checkbox" id="auto-study" ${learning.auto ? "checked" : ""}>Tự ôn khi rảnh</label><select id="study-interval" aria-label="Khoảng cách ôn tập">${[1,5,15,30].map(n => `<option value="${n}" ${learning.interval === n ? "selected" : ""}>Mỗi ${n} phút</option>`).join("")}</select></div></div>
    <div class="stats-row">${stat(sources.length,"Nguồn bạn đã chọn","book")}${stat(ready,"Nguồn sẵn sàng tra lại","check","sage")}${stat(sources.length-ready,"Nguồn đang chờ chuẩn bị","clock","peach")}</div>
    <div class="section-heading"><h2>Thư viện kiến thức <span class="count">${sources.length}/40</span></h2><button class="btn secondary" data-action="study-now">${icon("play")}Ôn một nguồn ngay</button></div>
    ${sources.length ? `<div class="source-list">${sources.map(source => `<article class="source-card"><span class="tile-icon ${source.status === "ready" ? "sage" : ""}">${icon("file")}</span><div><h3>${esc(source.title)}</h3><p>${source.characters.toLocaleString("vi")} ký tự${source.status === "ready" ? ` · ${source.chunk_count} đoạn · ${source.reviews} lần chuẩn bị` : " · chờ ôn tập"}</p></div><span class="tag ${source.status === "ready" ? "ready" : ""}">${source.status === "ready" ? "Sẵn sàng" : "Đang chờ"}</span><button class="icon-btn" data-source-delete="${esc(source.id)}" aria-label="Xóa nguồn học">${icon("trash")}</button></article>`).join("")}</div>` : empty("Chọn điều bạn muốn Mira biết","Bắt đầu với ghi chú về sở thích, dự án đang làm, hoặc nội dung bạn muốn học. Mỗi nguồn tối đa 32.000 ký tự; file phải là văn bản UTF-8.","book")}
    <div class="section-heading"><h2>Báo cáo gần đây</h2><p>Bạn có thể đọc lại khi quay về</p></div><div class="report-list">${learning.reports.map(r => `<details class="report-card"><summary>${icon("check")}<span>${esc(r.title)}</span><time>${esc(new Date(r.created_at).toLocaleString("vi",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}))}</time>${icon("chevron")}</summary><p>${esc(r.note)}</p></details>`).join("") || empty("Mira chưa có báo cáo mới",'Thêm tài liệu, sau đó nhấn “Ôn một nguồn ngay” hoặc bật chế độ tự ôn.',"clock")}</div>
    <div class="info-note">${icon("shield")}<span>Bước chuẩn bị chạy miễn phí trên máy, không gọi AI cloud. Các báo cáo chứa trích đoạn từ tài liệu của bạn. Tính năng này tạo kho kiến thức để Mira tham khảo khi chat; không tự huấn luyện model, đọc toàn bộ máy hay lướt web nền.</span></div></div>`;
}

const toolGroups = [
  ["Kết nối với bạn",[
    ["phone","phone","Chat trên điện thoại","Ghép nối qua Tailscale khi laptop đang bật.",""],
    ["phone_cloud","cloud","Điện thoại khi máy tắt","Mở cấu hình Mira web cloud của bạn.","sage"],
    ["telegram","chat","Telegram","Kết nối bot, nhắn Mira và nhận lịch nhắc.","peach"],
    ["reminders","clock","Lịch nhắc","Xem và quản lý những việc cần nhớ.","rose"]]],
  ["Cùng làm việc",[
    ["folder","folder","Thư mục làm việc","Chọn phạm vi file Mira được phép đọc.",""],
    ["file","file","Chọn file","Thêm yêu cầu về file trong thư mục đã chọn.","peach"],
    ["tests","play","Chạy kiểm thử","Chọn lệnh kiểm thử cho dự án của bạn.","sage"],
    ["export","file","Xuất cuộc trò chuyện","Lưu lịch sử hiện tại thành file văn bản.",""]]],
  ["Nhìn và hỗ trợ trên máy tính",[
    ["screen","screen","Chia sẻ màn hình","Chụp một ảnh; bạn xem trước rồi chọn gửi.",""],
    ["comment_screen","star","Mira nhận xét màn hình","Chia sẻ ảnh và hỏi Mira đang thấy gì.","rose"],
    ["desktop","shield","Điều khiển máy","Cấp quyền theo phiên; duyệt từng thao tác.","peach"],
    ["device","screen","Trạng thái PC","Cho Mira kiểm tra pin và tài nguyên máy.","sage"],
    ["web","search","Tra cứu web","Bật/tắt tìm kiếm khi trò chuyện.",""]]],
  ["Cùng chơi và cá nhân hóa",[
    ["game","game","Kết nối game","Mở game bridge và các thao tác bạn đã dạy.",""],
    ["avatar","image","Nhân vật Mira","Đổi ảnh nhân vật 2D trên app.","rose"],
    ["models","grid","Mô hình và tốc độ","Chọn mô hình, tải và tối ưu cho máy.","sage"],
    ["cloud","cloud","AI cloud","Chọn mô hình chạy trên máy chủ Ollama.",""],
    ["guide","book","Hướng dẫn cài đặt","Kiểm tra Ollama và các bước thiết lập.","peach"]]]
];

function renderTools(force = false) {
  const signature = JSON.stringify([state.config.desktop,state.config.device,state.config.web,state.folder]);
  if (!force && signature === toolsSignature) return;
  toolsSignature = signature;
  $("#view-tools").innerHTML = `<div class="page-content"><div class="page-heading"><div><span class="eyebrow">MỘT NƠI CHO MỌI VIỆC</span><h1>Cùng Mira làm nhiều hơn.</h1><p>Kết nối điện thoại, chia sẻ màn hình hoặc cùng làm việc trên máy tính. Các quyền của bạn vẫn được kiểm tra như trong Mira trước đây.</p></div></div>${toolGroups.map(([heading, tools]) => `<div class="section-heading"><h2>${heading}</h2></div><div class="tool-grid">${tools.map(([name,image,title,note,color]) => `<button class="tool-card ${state.config[name] ? "enabled" : ""}" data-tool="${name}"><span class="tile-icon ${color}">${icon(image)}</span><strong>${title}</strong><p>${note}</p>${icon("arrow")}${state.config[name] ? '<span class="tag ready">Đang bật · nhấn để tắt</span>' : ""}</button>`).join("")}</div>`).join("")}${state.folder ? `<div class="info-note">${icon("folder")}<span>Thư mục đã chọn: ${esc(state.folder)}<br><button class="text-btn" data-tool="clear_folder">Bỏ quyền thư mục này</button></span></div>` : ""}</div>`;
}

function renderSettings() {
  const c = state.config;
  const toggle = (key,title,note) => `<div class="toggle-setting"><div><strong>${title}</strong><p>${note}</p></div><label class="toggle"><input type="checkbox" name="${key}" ${c[key] ? "checked" : ""} aria-label="${title}"></label></div>`;
  $("#view-settings").innerHTML = `<form class="page-content" id="settings-form"><div class="page-heading"><div><span class="eyebrow">THEO CÁCH BẠN THÍCH</span><h1>Một Mira dành cho bạn.</h1><p>Chọn giọng điệu, mô hình và giao diện. Mô hình cloud vẫn cần bạn đồng ý trước khi gửi dữ liệu.</p></div></div><div class="settings-grid"><section class="settings-card"><h2>Mô hình & cá tính</h2><p>Thay đổi cách Mira trò chuyện với bạn.</p>${field("Tên trợ lý","name",state.name,40)}<div class="field"><label for="settings-model">Mô hình Ollama</label><div class="settings-model-row"><input id="settings-model" name="model" list="model-list" maxlength="100" value="${esc(c.model)}" required><button type="button" class="icon-btn" data-tool="check" aria-label="Kiểm tra mô hình">${icon("refresh")}</button></div><datalist id="model-list">${state.models.map(m => `<option value="${esc(m)}"></option>`).join("")}</datalist><small>${esc(state.health)}</small></div><div class="field"><label for="persona-note">Cách bạn muốn Mira nói chuyện</label><textarea id="persona-note" name="persona_note" rows="4" maxlength="400" placeholder="Ví dụ: Xưng em–anh, nói ngắn gọn, vui vẻ; khi không biết thì nói thật.">${esc(c.persona_note)}</textarea><small>Những ví dụ cụ thể trong trang Bộ nhớ sẽ giúp Mira hiểu sở thích của bạn hơn.</small></div><div class="inline-links"><button type="button" class="btn secondary" data-tool="models">${icon("grid")}Mô hình & tốc độ</button><button type="button" class="btn secondary" data-tool="cloud">${icon("cloud")}AI cloud</button></div></section><section class="settings-card"><h2>Trải nghiệm của bạn</h2><p>Điều chỉnh để hợp với nhịp làm việc.</p>${toggle("playful","Mira hoạt bát","Tự nhiên, có cá tính và đùa nhẹ khi phù hợp.")}${toggle("fast","Ưu tiên tốc độ","Dùng ngữ cảnh và câu trả lời gọn hơn.")}${toggle("deep","Suy luận sâu","Dành thêm thời gian cho yêu cầu phức tạp.")}${toggle("voice_auto","Tự đọc câu trả lời","Dùng giọng đã cài trên Windows.")}<hr class="section-divider"><div class="field"><label for="theme-choice">Giao diện</label><select id="theme-choice" name="theme"><option value="light" ${c.theme === "light" ? "selected" : ""}>Sáng · nhẹ nhàng</option><option value="dark" ${c.theme === "dark" ? "selected" : ""}>Tối · yên tĩnh</option></select></div><div class="info-note">${icon("shield")}<span>Quyền điều khiển và đọc trạng thái máy hết khi đóng app. Các công cụ nằm trong trang Công cụ.</span></div></section></div><div class="settings-actions"><button type="button" class="btn secondary" data-action="quit">Đóng Mira</button><button type="submit" class="btn primary">${icon("check")}Lưu cài đặt</button></div><p class="local-note">Mira Studio 3 · Giao diện chạy trên máy này bằng Edge/Chrome, không cần gói giao diện trả phí. Lịch sử chat và bộ nhớ cũ được giữ trong thư mục dữ liệu Mira của bạn.</p></form>`;
}

function showView(next) {
  if (!titles[next]) next = "chat";
  view = next;
  $$(".view").forEach(node => node.classList.toggle("active", node.id === "view-" + next));
  $$("[data-view].nav-item").forEach(node => node.classList.toggle("active", node.dataset.view === next));
  $("#view-title").textContent = titles[next];
  $(".sidebar").classList.remove("open");
  $("#sidebar-shade").hidden = true;
  if (state) {
    if (view === "memory") renderMemory(true);
    if (view === "study") renderStudy(true);
    if (view === "tools") renderTools(true);
    if (view === "settings") renderSettings();
    if (view === "chat") renderFeed();
  }
}

function render(next) {
  const previous = state;
  if (previous && previous.chat_id !== next.chat_id) {
    drafts.set(previous.chat_id,$("#message-input").value);
    $("#message-input").value = drafts.get(next.chat_id) || "";
    resizeInput();
  }
  state = next;
  document.title = state.window_title || "Mira Studio";
  document.body.dataset.theme = state.config.theme;
  $("#chat-title").textContent = state.title;
  $("#model-label").textContent = state.config.model;
  $("#model-label").title = state.health;
  $("#chat-status").textContent = state.status;
  $("#retry-btn").hidden = !state.retry;
  $("#send-btn").disabled = state.busy || sending;
  $("#send-btn").setAttribute("aria-label", state.busy ? "Mira đang trả lời" : "Gửi tin nhắn");
  $("#new-chat").disabled = state.busy;
  $("#dictate").disabled = !state.config.windows || state.busy;
  $("#attachment-row").hidden = !state.attachment;
  $("#attachment-name").textContent = state.attachment || "";
  renderSidebar(); renderCompanion();
  if (view === "chat") renderFeed();
  if (view === "memory") renderMemory();
  if (view === "study") renderStudy();
  if (view === "tools") renderTools();
  // Never replace a settings form while the user is editing it.
  if (!previous && view === "settings") renderSettings();
  $("#startup").hidden = true;
}

async function poll() {
  if (!csrf || polling || stopped) return;
  polling = true;
  lastPoll = Date.now();
  try { render(await request("/api/state")); }
  catch (error) {
    $("#connection-title").textContent = "Chưa kết nối";
    $("#connection-dot").classList.add("offline");
    $("#chat-status").textContent = error.message;
  } finally { polling = false; }
}

async function connect() {
  $("#reconnect").hidden = true;
  try {
    const token = new URLSearchParams(location.hash.slice(1)).get("session") || "";
    const session = await request("/api/session", {token});
    csrf = session.csrf;
    history.replaceState(null,"",location.pathname);
    render(await request("/api/state"));
  } catch (error) {
    $("#startup-note").textContent = error.message;
    $("#reconnect").hidden = false;
  }
}

function resizeInput() {
  const input = $("#message-input");
  input.style.height = "auto";
  input.style.height = Math.min(180,input.scrollHeight) + "px";
}

async function sendMessage(event) {
  event?.preventDefault();
  if (!state || state.busy || sending) return;
  const input = $("#message-input"), text = input.value.trim();
  if (!text && !state.attachment) return;
  sending = true; $("#send-btn").disabled = true;
  try {
    const result = await command("send", {text});
    if (result.sent) { input.value = ""; drafts.delete(state.chat_id); resizeInput(); }
  } catch (error) { toast(error.message,true); }
  finally { sending = false; $("#send-btn").disabled = Boolean(state?.busy); input.focus(); }
}

function memoryEditor(id = null, candidateId = null) {
  const memory = id ? state.memories.find(m => m.id === id) : candidateId ? state.learning.candidates.find(c => c.id === candidateId) : null;
  openModal({title:candidateId ? "Mira nên nhớ điều này?" : id ? "Sửa điều cần nhớ" : "Dạy Mira nhớ",
    body:`<p class="modal-intro">Viết một điều cụ thể, đúng với bạn. Ký ức này sẽ được dùng trong các cuộc trò chuyện phù hợp.</p>${field("Điều bạn muốn Mira nhớ","text",memory?.text || "",500,4)}${candidateId ? `<small class="local-note">Nguồn: lời bạn nói trong một cuộc trò chuyện. Bạn có thể sửa trước khi lưu.</small>` : ""}`,
    saveLabel:candidateId ? "Lưu vào bộ nhớ" : "Lưu ký ức",
    onSave: values => command(candidateId ? "candidate_decide" : id ? "memory_edit" : "memory_add",{...values,id:candidateId || id,accept:true})});
}

function exampleEditor(index = null) {
  let requestText = "", answer = "";
  if (index !== null) {
    answer = state.messages[index]?.content.slice(0,500) || "";
    for (let i = index-1; i >= 0; i--) {
      if (state.messages[i].role === "user") { requestText = state.messages[i].content.slice(0,500); break; }
    }
  }
  openModal({title:"Dạy Mira cách bạn thích",eyebrow:"HỌC TỪ PHẢN HỒI CỦA BẠN",
    body:`<p class="modal-intro">Sửa câu trả lời thành cách bạn muốn Mira nói. Ví dụ này được lưu để tham khảo khi gặp câu hỏi tương tự.</p>${field("Từ khóa liên quan","tags","",500,0,"Ví dụ: Python, học tập, tâm sự. Mỗi trường tối đa 500 ký tự.")}${field("Câu hỏi mẫu","request",requestText,500,2)}${field("Câu trả lời bạn muốn","answer",answer,500,4)}`,
    saveLabel:"Dạy Mira",onSave:values => command("example_add",values)});
}

function chatOptions(id) {
  const chat = state.chats.find(item => item.id === id);
  if (!chat) return;
  openModal({title:"Cuộc trò chuyện",body:`${field("Tên cuộc trò chuyện","title",chat.title,80)}<div class="modal-links"><button type="button" class="btn secondary" data-tool="export">${icon("file")}Xuất cuộc trò chuyện đang mở</button><button type="button" class="btn secondary" data-chat-delete="${esc(id)}">${icon("trash")}Xóa cuộc trò chuyện này</button></div>`,
    saveLabel:"Đổi tên",onSave:values => command("chat_rename",{id,...values})});
}

async function runTool(name) {
  if (!state) return;
  if (name === "file") showView("chat");
  const messageTimer = setTimeout(() => toast("Công cụ đang mở. Hãy xem hộp thoại Mira trên máy tính."),1300);
  try {
    const result = await command("tool",{name,draft:$("#message-input").value});
    if (typeof result.draft === "string") { $("#message-input").value = result.draft; resizeInput(); $("#message-input").focus(); }
  } catch(error) { toast(error.message,true); }
  finally { clearTimeout(messageTimer); }
}

function recordActivity() {
  if (csrf && Date.now() - lastActivity > 15000) {
    lastActivity = Date.now();
    request("/api/command",{operation:"activity",data:{}}).catch(() => {});
  }
}
document.addEventListener("click", recordActivity);
document.addEventListener("keydown", recordActivity);
document.addEventListener("click", async event => {
  const button = event.target.closest("button,a.brand");
  if (!button) return;
  try {
    if (button.dataset.view) { showView(button.dataset.view); return; }
    if (button.matches("a.brand")) { event.preventDefault(); showView("chat"); return; }
    if (button.dataset.tool) { await runTool(button.dataset.tool); return; }
    if (!state) return;
    if (button.dataset.prompt) { $("#message-input").value = button.dataset.prompt; resizeInput(); $("#message-input").focus(); return; }
    if (button.dataset.chat) { await command("chat_select",{id:button.dataset.chat}); showView("chat"); return; }
    if (button.dataset.chatOptions) { chatOptions(button.dataset.chatOptions); return; }
    if (button.dataset.chatDelete) { confirmAction("Xóa cuộc trò chuyện?","Lịch sử của cuộc trò chuyện này sẽ được xóa khỏi máy này.","chat_delete",{id:button.dataset.chatDelete}); return; }
    if (button.dataset.memoryEdit) { memoryEditor(button.dataset.memoryEdit); return; }
    if (button.dataset.memoryDelete) { confirmAction("Quên điều này?","Ký ức này sẽ không còn được gửi kèm trong những lần chat sau.","memory_delete",{id:button.dataset.memoryDelete}); return; }
    if (button.dataset.candidateAccept) { memoryEditor(null,button.dataset.candidateAccept); return; }
    if (button.dataset.candidateIgnore) { await command("candidate_decide",{id:button.dataset.candidateIgnore,accept:false}); return; }
    if (button.dataset.preferenceDelete) { confirmAction("Xóa cách trả lời đã dạy?","Quy tắc hoặc ví dụ này sẽ được bỏ khỏi bộ sở thích.","preference_delete",{id:button.dataset.preferenceDelete}); return; }
    if (button.dataset.sourceDelete) { confirmAction("Xóa nguồn kiến thức?","Mira sẽ bỏ tài liệu và báo cáo của nguồn này khỏi kho kiến thức.","source_delete",{id:button.dataset.sourceDelete}); return; }
    if (button.dataset.copy !== undefined) { await navigator.clipboard.writeText(state.messages[Number(button.dataset.copy)].content); toast("Đã sao chép câu trả lời."); return; }
    if (button.dataset.feedback !== undefined) { exampleEditor(Number(button.dataset.feedback)); return; }
    switch(button.dataset.action) {
      case "memory-add": memoryEditor(); break;
      case "rule-add": openModal({title:"Mira nên trò chuyện thế nào?",body:field("Quy tắc bạn muốn","text","",500,4),onSave:values => command("rule_add",values)}); break;
      case "example-add": exampleEditor(); break;
      case "source-add": openModal({title:"Một điều mới để Mira học",body:`<p class="modal-intro">Chọn nội dung bạn muốn Mira biết. Sau khi chuẩn bị, Mira sẽ tham khảo những đoạn liên quan lúc chat.</p>${field("Tên nguồn học","title","",100)}${field("Nội dung bạn chọn","text","",32000,10,"Văn bản hoặc Markdown, tối đa 32.000 ký tự. Chỉ thêm nội dung bạn đồng ý cho Mira dùng.")}`,saveLabel:"Thêm vào hàng đợi",onSave:values => command("source_add",values)}); break;
      case "source-import": await command("source_import"); break;
      case "study-now": await command("study_now"); toast("Mira đã chuẩn bị một nguồn học."); break;
      case "quit": confirmAction("Đóng Mira?","Chat điện thoại qua laptop và việc tự ôn sẽ dừng. Các dữ liệu đã lưu vẫn được giữ.","quit",{}); break;
    }
  } catch(error) { toast(error.message,true); }
});

document.addEventListener("change",async event => {
  try {
    if (event.target.id === "auto-study" || event.target.id === "study-interval") {
      await command("study_config",{auto:$("#auto-study").checked,interval:Number($("#study-interval").value)});
    }
    if (event.target.id === "theme-choice") document.body.dataset.theme = event.target.value;
  } catch(error) { toast(error.message,true); renderStudy(true); }
});

document.addEventListener("submit", async event => {
  if (event.target.id !== "settings-form") return;
  event.preventDefault();
  const form = event.target, values = Object.fromEntries(new FormData(form));
  for (const name of ["fast","deep","playful","voice_auto"]) values[name] = form.elements[name].checked;
  const save = $('button[type="submit"]',form); save.disabled = true;
  try { await command("settings",values); toast("Đã lưu cài đặt của bạn."); }
  catch(error) { toast(error.message,true); }
  finally { save.disabled = false; }
});

$("#chat-form").addEventListener("submit",sendMessage);
$("#message-input").addEventListener("input",resizeInput);
$("#message-input").addEventListener("keydown",event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendMessage(); }
});
$("#new-chat").addEventListener("click",async () => {
  try { await command("chat_new"); showView("chat"); $("#message-input").focus(); }
  catch(error) { toast(error.message,true); }
});
$("#retry-btn").addEventListener("click",async () => {
  try { await command("retry"); } catch(error) { toast(error.message,true); }
});
$("#chat-menu").addEventListener("click",() => state && chatOptions(state.chat_id));
$("#dictate").addEventListener("click",async () => {
  $("#message-input").focus();
  try { await command("dictation"); toast("Windows đang nhập giọng nói. Xem lại câu và nhấn Gửi."); }
  catch(error) { toast(error.message,true); }
});
$("#history-search").addEventListener("input",() => state && renderSidebar());
$("#search-toggle").addEventListener("click",() => {
  const input = $("#history-search"); input.hidden = !input.hidden;
  if (!input.hidden) input.focus(); else { input.value = ""; if(state) renderSidebar(); }
});
$("#menu-toggle").addEventListener("click",() => {
  const open = $(".sidebar").classList.toggle("open"); $("#sidebar-shade").hidden = !open;
});
$("#sidebar-shade").addEventListener("click",() => { $(".sidebar").classList.remove("open"); $("#sidebar-shade").hidden = true; });
$("#modal-close").addEventListener("click",() => $("#modal").close());
$("#modal-cancel").addEventListener("click",() => $("#modal").close());
$("#modal-form").addEventListener("submit",async event => {
  event.preventDefault();
  if (!modalSubmit) return;
  const dialog = $("#modal"), save = $("#modal-save");
  const values = Object.fromEntries(new FormData(event.target));
  save.disabled = true;
  $(".modal-error",dialog)?.remove();
  try { await modalSubmit(values); dialog.close(); toast("Đã lưu thay đổi."); }
  catch(error) { const note = document.createElement("p"); note.className = "modal-error"; note.textContent = error.message; $("#modal-body").append(note); }
  finally { save.disabled = false; }
});
$("#reconnect").addEventListener("click",connect);
document.addEventListener("keydown",event => {
  if (event.key.toLowerCase() === "n" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest("input,textarea,select") && !$("#modal").open) { event.preventDefault(); $("#new-chat").click(); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("#history-search").hidden = false; $("#history-search").focus(); }
});
window.addEventListener("pagehide",() => {
  if (!csrf) return;
  fetch("/api/command",{method:"POST",headers:{"Content-Type":"application/json","X-Mira-CSRF":csrf},body:JSON.stringify({operation:"window_closing",data:{}}),keepalive:true}).catch(() => {});
});
$("#today").textContent = new Date().toLocaleDateString("vi",{weekday:"short",day:"2-digit",month:"long"});
connect();
setInterval(() => {
  const interval = document.hidden ? 15000 : state?.busy ? 250 : 2500;
  if (Date.now() - lastPoll >= interval) poll();
},250);
