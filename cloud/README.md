# Mira trên điện thoại — laptop tắt vẫn dùng được

Bản này chạy trên **Cloudflare Workers Free**, dùng model **GLM-4.7-Flash** qua Workers AI, lưu chat/ghi chú/lịch nhắc trong D1. Mở URL riêng `https://mira-phone.<subdomain>.workers.dev/` trên điện thoại để chat. Nếu muốn nhận thông báo lịch ngay cả khi đóng trang, kết nối **một bot Telegram riêng**. Sau khi cài một lần, bạn không cần để laptop bật.

> Chat, lịch, ghi chú riêng và file vẫn ở hai nơi riêng. Các mục trong **Dạy Mira / bộ nhớ** có thể chuyển thủ công giữa desktop và cloud bằng nút gửi/lấy. Cloud Mira không truy cập được pin, màn hình, file hay chuột của laptop đang tắt. Khi laptop bật, có thể dùng thêm trang Tailscale sẵn có để làm việc với PC theo từng quyền bạn đã cấp.

## Chi phí và giới hạn

Chọn **Workers Free** của Cloudflare, không đăng ký gói trả phí hoặc nhập thẻ nếu chỉ muốn dùng miễn phí. Theo [giá Workers AI hiện hành](https://developers.cloudflare.com/workers-ai/platform/pricing/), tài khoản Free có 10.000 Neurons/ngày, vượt hạn mức sẽ trả lỗi và chờ ngày mới; model [GLM-4.7-Flash](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/) thuộc các model được dùng ở gói Free theo [thông báo của Cloudflare](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/). [D1 cũng có gói Free](https://developers.cloudflare.com/d1/reference/faq/), [Workers Free có giới hạn request/ngày](https://developers.cloudflare.com/workers/platform/limits/). Hạn mức và danh sách model có thể đổi: hãy kiểm tra trang chính thức trước khi cài. Không có gói AI miễn phí vô hạn hoặc bảo đảm luôn sẵn sàng.

## Cài một lần trên máy tính

1. Tạo tài khoản [Cloudflare](https://dash.cloudflare.com/sign-up) và chọn **Free**. Cài [Node.js](https://nodejs.org/en/download) để có `npx` và dùng Python 3.11+ sẵn có trên máy. Không cần tải model AI về laptop.
2. Giải nén đầy đủ bản Mira mới; mở PowerShell trong thư mục `cloud` cạnh `mira`, `run_mira.py`, rồi chạy `python setup.py` (hoặc `py setup.py`). Đăng nhập Cloudflare trên trình duyệt khi Wrangler yêu cầu. Chương trình tạo D1, chạy migration, deploy Worker và cài một **khóa truy cập ngẫu nhiên** dài vào Cloudflare Secrets.
3. **Lưu khóa được in ra cuối lệnh** trong trình quản lý mật khẩu. Ghi lại URL `https://mira-phone.<subdomain>.workers.dev/` mà lệnh deploy in ra. Mở URL đó trên điện thoại, nhập khóa, chat thử. Bạn có thể thêm trang vào màn hình chính bằng menu trình duyệt. Mở lại từ thẻ mới sẽ phải nhập khóa; thẻ cũ giữ khóa trong phiên trình duyệt.
4. Chọn **Ghi nhớ** trong trang điện thoại, tự nhập vài sở thích hoặc chép ghi chú phù hợp từ Mira trên PC. Dữ liệu ghi vào tài khoản Cloudflare của bạn và được gửi tới model Workers AI khi chat.

**Nếu muốn làm thủ công** (trong thư mục `cloud`): trên Windows PowerShell, chạy `npx.cmd wrangler login`, `npx.cmd wrangler d1 create mira-phone --no-update-config`, **sau đó** chép `wrangler.toml.example` thành `wrangler.toml`, thay `REPLACE_WITH_YOUR_D1_DATABASE_ID` bằng `database_id` lệnh vừa in ra; tiếp tục `npx.cmd wrangler d1 migrations apply mira-phone --remote`, `npx.cmd wrangler deploy`, `npx.cmd wrangler secret put MIRA_ACCESS_KEY` và nhập một khóa bí mật tự tạo từ 24 ký tự trở lên. Không commit khóa vào GitHub. Trên macOS/Linux, thay `npx.cmd` bằng `npx`.

**Sau khi sửa web hoặc cập nhật Mira:** mở PowerShell trong đúng thư mục `cloud` đã cài (có file `wrangler.toml`), chạy **`npx.cmd wrangler d1 migrations apply mira-phone --remote` trước**, sau đó chạy `npx.cmd wrangler deploy` và tải lại trang trên điện thoại. Bản này thêm bảng bộ nhớ chung; bỏ qua migration sẽ khiến trang chưa chạy được. Lệnh deploy cập nhật `public/` và `worker.mjs` lên cùng Worker cũ; không cần chạy lại `setup.py` vì script thiết lập sẽ tạo khóa đăng nhập mới. Nếu PowerShell báo không chạy được `npx.ps1` do Execution Policy, dùng `npx.cmd` như trên, không cần đổi chính sách chạy script.

## Nói chuyện bằng giọng nói

Mở tab **Trò chuyện** trên điện thoại, nhấn **🎙**, cấp quyền microphone cho trình duyệt rồi nói tiếng Việt. Khi bạn ngừng nói, Mira gửi câu đã nhận dạng và đọc câu trả lời; nhấn **Dừng đọc** nếu muốn ngắt. Tích **Mira đọc câu trả lời** nếu muốn cả tin gõ tay cũng được đọc. Bạn có thể nhấn **Nghe lại** bên dưới tin Mira để chủ động phát tiếng khi trình duyệt chặn tự phát. Microphone chỉ bật khi bạn nhấn, không nghe ở nền hoặc khi rời trang. Tính năng nhận giọng nói phụ thuộc trình duyệt; một số trình duyệt xử lý âm thanh qua máy chủ của chính trình duyệt và cần mạng, có thể không hỗ trợ tiếng Việt. Nếu không thấy nút khả dụng, vẫn có thể dùng bàn phím và đọc tin nhắn. Giọng đọc dùng giọng có sẵn trên điện thoại; nếu thiếu giọng tiếng Việt, phát âm có thể không chuẩn. Không cần trả phí thêm cho nút này, nhưng mỗi tin gửi AI vẫn tính vào hạn mức cloud.

## Mang bộ nhớ từ PC sang điện thoại

1. Cập nhật app desktop và cloud như trên. Trên PC mở **Dạy Mira / bộ nhớ**, nhập các mục bạn muốn dùng chung.
2. Chọn **↑ Gửi bộ nhớ lên điện thoại**, nhập URL `https://...workers.dev/` và khóa truy cập của bản Mira cloud. Đọc số lượng mục ở hai phía rồi xác nhận. URL được lưu trên PC; **khóa chỉ giữ trong RAM đến khi tắt app**.
3. Mở tab **Ghi nhớ** trên điện thoại để thêm hoặc quên từng mục. Khi muốn dùng bản mới nhất trên PC, chọn **↓ Lấy bộ nhớ về PC** trong cùng cửa sổ desktop.

Mỗi lần gửi/lấy sẽ **thay toàn bộ danh sách mục ở phía nhận** sau khi hỏi xác nhận. Nên lấy về trước khi gửi nếu vừa sửa trên điện thoại. **Ghi chú cá nhân** trong trang điện thoại vẫn riêng và không bị thay; bộ sở thích JSON, lịch sử chat, lịch nhắc và file trên PC không đồng bộ. Nếu PC bị tắt, Mira cloud vẫn dùng các mục đã gửi trước đó, nhưng không cập nhật các mục mới trên PC cho đến lần gửi tiếp theo.

Nếu vừa cập nhật cách Mira trả lời, hãy gửi một tin nhắn mới để thử; các câu trả lời cũ trong lịch sử không tự đổi. Bạn có thể chọn **Trò chuyện → Xóa lịch sử** để bắt đầu lại, nhưng thao tác này cũng xóa lịch sử chat qua Telegram trên cùng Mira cloud.

## Nhận lịch qua Telegram khi laptop tắt

1. Vào [@BotFather](https://t.me/BotFather) tạo **bot mới**, giữ token riêng. Không dùng cùng token của bot Mira desktop: Telegram webhook trên cloud sẽ ngăn bot long polling trên PC nhận tin.
2. Mở bot mới trên điện thoại, bấm **Start** hoặc nhắn `/start`.
3. Tại thư mục `cloud` trên PC, chạy `python setup_telegram.py`, dán token vào lời nhắc ẩn, kiểm tra Telegram ID của **chính bạn** rồi nhập ID. Nhập URL Worker đã có ở bước cài cloud. Script cài token/ID/webhook secret bằng Cloudflare Secrets và đăng ký webhook. Chỉ tin nhắn riêng từ ID đã chọn mới được xử lý.
4. Mở lại trang Mira trên điện thoại. Tab **Lịch nhắc** cho phép chọn thời gian theo múi giờ điện thoại; khi đến hạn, Worker gửi qua bot Telegram. Cron chạy mỗi phút ở UTC; thông báo có thể đến muộn hơn một chút do mạng, Telegram hoặc thời gian kích hoạt Cron của Cloudflare. Tắt laptop không ảnh hưởng Worker đã deploy.

Trong Telegram, gửi tin nhắn bất kỳ để chat với Mira. Các lệnh: `/help`, `/gio`, `/lich`, `/nhac 30p | uống nước`, `/nhac 2h | đứng dậy`, `/nhac 2026-10-01T09:00:00+07:00 | đi họp`, `/xoa <mã 8 ký tự>` từ `/lich`. Giờ tuyệt đối phải có múi giờ như `+07:00` hoặc `Z`; tab Lịch nhắc tự chuyển giờ điện thoại sang UTC. Lịch hiển thị cho bot theo `MIRA_TIMEZONE` trong `wrangler.toml` (mặc định `Asia/Ho_Chi_Minh`); sửa biến rồi deploy lại nếu cần. Nếu chưa cài bot, lịch vẫn lưu được nhưng **không tự hiện thông báo khi đóng trang**.

Telegram cần [webhook HTTPS và secret_token](https://core.telegram.org/bots/api#setwebhook); lúc `setWebhook` hoạt động, long polling `getUpdates` của cùng bot sẽ ngừng. Để ngắt bot trên Windows, dùng `npx.cmd wrangler secret delete TELEGRAM_BOT_TOKEN` và thu hồi token cũ tại BotFather. Đừng gửi token, khóa Mira hay dữ liệu nhạy cảm lên chat công khai.

## Khi laptop đang bật

Trong app desktop Mira, chọn **Kết nối khi máy bật** → bật giao diện Tailscale, mở `tailscale serve --bg 8765` theo hướng dẫn, ghép nối và chọn từng quyền cần dùng. Tab **Máy tính** trong trang cloud cho lưu địa chỉ HTTPS `*.ts.net` (chỉ lưu trên điện thoại) để mở nhanh trang riêng của PC. Trang cloud **không tự xem trạng thái máy** và không chuyển quyền PC sang cloud. Nếu laptop ngủ hoặc tắt, đường dẫn Tailscale và điều khiển từ xa không hoạt động.

## Dữ liệu và an toàn

- Trang cloud cần khóa cá nhân ngẫu nhiên tối thiểu 24 ký tự; mỗi yêu cầu API phải gửi khóa đó qua HTTPS, giữ trong `sessionStorage` của thẻ trình duyệt. Không cho người khác dùng chung khóa hay máy đã đăng nhập. Chọn **Máy tính → Khóa Mira** để xóa khóa ở thẻ đang mở.
- Chat và ghi chú lưu trong D1, gửi trong yêu cầu suy luận tới Workers AI. Telegram cũng nhận nội dung tin nhắn và lịch qua bot do bạn tạo. Không gửi mật khẩu, API key hoặc tài liệu cần bảo mật nghiêm ngặt.
- Tab **Trò chuyện → Xóa lịch sử** xóa toàn bộ lịch sử cloud, bao gồm từ Telegram. Lịch và ghi chú được lưu riêng. Chỉ các mục bộ nhớ bạn chọn gửi/lấy mới được dùng ở cả desktop và cloud.
- Có thể tự đặt lịch trên điện thoại ngay cả khi chưa cấu hình Telegram, nhưng muốn nhận thông báo khi trang đóng phải kết nối bot. Lịch quan trọng cần báo thức của điện thoại làm dự phòng.
