# Mira — trợ lý AI cá nhân trên máy tính

Mira là ứng dụng desktop dành cho Windows, trò chuyện bằng tiếng Việt qua Ollama. Bạn có thể dùng mô hình trên máy hoặc chọn mô hình Ollama Cloud cho máy yếu. Mira giúp giải thích, viết code, tìm/đọc file, kiểm tra cú pháp Python và đề xuất sửa file trong thư mục bạn chọn. Tên gọi và cách xưng hô của Mira có thể chỉnh trong **Mô hình & cài đặt**.

## Chạy Mira trên Windows

1. Cài [Python 3.11+](https://www.python.org/downloads/) và chọn **Add python.exe to PATH** trong trình cài đặt.
2. Cài [Ollama cho Windows](https://ollama.com/download/windows) và mở Ollama.
3. Nếu dùng AI trên máy, mở PowerShell, chạy `ollama pull qwen3:4b` và đợi tải xong. Nếu máy yếu, bỏ qua bước tải mô hình lớn và làm theo mục **AI cloud cho máy yếu** bên dưới.
4. Giải nén ZIP, nhấn đúp **`start_windows.bat`**. Nếu đã cài Mira trước đó, hãy đóng cửa sổ Mira cũ rồi chép đè toàn bộ file của ZIP mới vào đúng thư mục đang chạy `start_windows.bat`; mở lại ứng dụng để thấy giao diện mới. Không cần `pip install` cho bản cơ bản.
5. Màn hình mở thẳng vào chat: mỗi tin nhắn nằm trong thẻ riêng giữa màn hình; ô **NHẮN MIRA** ở cuối trang. Bấm **Gửi** hoặc Enter; **Shift+Enter** xuống dòng. Bốn gợi ý bắt đầu hiện khi mở cuộc trò chuyện mới. Khi cửa sổ đủ rộng, bảng **TRUNG TÂM MIRA** bên phải có trạng thái mô hình và lối tắt; cửa sổ nhỏ dùng **Mở tất cả công cụ** ở thanh bên. Bấm **Sao chép** trên từng thẻ để lấy nội dung tin đó, hoặc ở cuối trang để lấy câu trả lời mới nhất.

Máy yếu có thể mất thời gian để tạo câu trả lời đầu tiên. Khi mô hình chưa được tải, Mira sẽ hiển thị hướng dẫn ngay trên màn hình. Nếu Python Launcher (`py`) không có, file `.bat` sẽ thử `python`.

### Nếu Mira trả lời chậm

- Bản này **hiển thị nội dung dần** ngay khi Ollama bắt đầu tạo chữ. Thời gian suy luận thật vẫn tùy CPU/GPU và RAM trên máy; lần đầu tải mô hình thường chậm hơn.
- Trong **Mô hình & cài đặt**, bật **Ưu tiên tốc độ** (mặc định). Mira gửi ít lịch sử và ví dụ phù hợp hơn, dùng ngữ cảnh gọn; những cuộc trò chuyện dài hoặc file code lớn có thể cần tắt chế độ này để giữ thêm ngữ cảnh.
- Muốn giảm tải thêm, chạy `ollama pull qwen3:1.7b`, mở **Mô hình & cài đặt**, chọn `qwen3:1.7b`. Mô hình nhỏ hơn thường nhanh hơn nhưng có thể kém chính xác khi sửa code phức tạp. `qwen3:1.7b` chỉ dùng văn bản, không nhìn ảnh; khi gửi ảnh hãy chọn mô hình vision như `qwen3-vl:4b`.
- Mira giữ mô hình cục bộ sẵn trong Ollama trong khoảng **15 phút** giữa các yêu cầu để tránh tải lại; điều này có thể giữ RAM đang dùng. Mô hình cloud chạy trên máy chủ và phụ thuộc tốc độ mạng, tải máy chủ, hạn mức tài khoản.

### AI cloud cho máy yếu: dùng gói Free có hạn mức

1. Cài và mở Ollama, mở PowerShell, chạy `ollama signin`. Việc đăng nhập thực hiện với Ollama, không nhập mật khẩu vào Mira.
2. Xem [gói Free và mô hình Starter hiện áp dụng](https://ollama.com/pricing) trong tài khoản. Chọn một mô hình cloud bạn được phép dùng, ưu tiên mô hình hỗ trợ gọi công cụ nếu muốn Mira làm việc với file/code. Chạy `ollama pull <tên-mô-hình-cloud>` để đăng ký mô hình. Ví dụ cú pháp tên là `gemma4:cloud`; đây **không phải cam kết** mô hình cụ thể đó nằm trong hạn mức Free của tài khoản bạn. Lệnh pull cho cloud không tải trọng số hàng GB.
3. Mở Mira → **☁ AI cloud cho máy yếu** → **Kiểm tra lại** → chọn mô hình cloud đã xuất hiện → **Dùng cloud**. Mira sẽ hỏi bạn trước khi gửi nội dung chat, ghi nhớ/sở thích liên quan, ảnh hoặc phần file mà Mira được cấp quyền đọc lên Ollama Cloud. Mục này có nút chuyển về mô hình trên máy và thu hồi đồng ý.

Gói Free của Ollama có lượt dùng Starter hằng tháng, không phải cloud miễn phí vô hạn; mô hình có quyền truy cập và hạn mức có thể thay đổi. Ollama có thể dùng credit đã mua của bạn khi hết lượt miễn phí; Mira không nạp credit, không nhập thẻ và không thể khóa khoản credit đã mua trên tài khoản. Nếu chỉ muốn miễn phí, hãy dùng gói Free và không mua credit; kiểm tra [lượt dùng tài khoản](https://ollama.com/settings) trước khi chat. Mô hình cloud cần Internet và có thể chậm lúc mạng yếu hoặc máy chủ bận. Nếu gói Free hết lượt, hãy chờ kỳ làm mới hoặc quay về AI trên máy.

### Mô hình mạnh hơn và tốc độ thật trên máy

Trong thanh bên chọn **Mở tất cả công cụ → Mô hình mạnh & tốc độ**. Bạn có thể bấm **Tải 9B** để cài `qwen3.5:9b` miễn phí bằng Ollama (khoảng 6,6 GB dữ liệu tải), hoặc **Tải 4B** cho `qwen3.5:4b` (khoảng 3,4 GB). Sau khi tải, Mira tự chọn mô hình đó. Cả hai nhận ảnh và có khả năng gọi công cụ. Nếu muốn cài thủ công, dùng `ollama pull qwen3.5:9b` trong PowerShell rồi chọn trong **Mô hình & cài đặt**.

Nút **Đo tốc độ** cho các mô hình đã cài tạo một câu ngắn trên chính máy bạn, hiển thị token/giây, thời gian tải mô hình và tổng thời gian. Đây chỉ là phép đo một lượt ngắn, không đo chất lượng câu trả lời. Mô hình 9B có thể hiểu và làm việc phức tạp tốt hơn nhưng **không bảo đảm nhanh hơn** 4B; nếu vượt dung lượng RAM/VRAM thì sẽ chậm rõ rệt. Chọn mô hình theo kết quả đo và mức độ hữu ích của câu trả lời thực tế.

**Suy luận sâu** trong cửa sổ này cho phép mô hình có hỗ trợ suy luận dành thêm thời gian cho việc khó. Chế độ này tắt mặc định để chat nhanh; bật lên có thể khiến Mira chờ lâu trước khi hiện chữ đầu tiên. Chế độ **Ưu tiên tốc độ** và **Suy luận sâu** được lưu riêng.

## Xem giờ, tra cứu web và hỗ trợ trực tiếp trên màn hình

- Hỏi **“Mấy giờ rồi?”** để nhận ngay ngày giờ theo đồng hồ trên máy đang chạy Mira, không tốn lượt mô hình. Giờ trên điện thoại có thể khác múi giờ với máy tính.
- Bật **🌐 Cho Mira tra cứu web** trong bảng bên phải, hoặc qua **Mở tất cả công cụ → Bật / tắt tra cứu web** khi cửa sổ hẹp. Xác nhận việc gửi câu tìm kiếm ra mạng. Sau đó hỏi “Tìm trên mạng về …” hoặc dùng **/web từ khóa** để nhận tiêu đề, trích đoạn và URL nguồn ngay cả khi mô hình không hỗ trợ gọi công cụ. Mira không đọc toàn bộ trang; khi DuckDuckGo không trả kết quả, Mira thử Wikipedia và ghi rõ phạm vi nguồn. Tính năng không đòi API trả phí; mạng hoặc dịch vụ tìm kiếm có thể hạn chế lượt tra cứu.
- Bấm **▣ Màn hình** cạnh ô chat. Mira thu một ảnh **màn hình chính** trên Windows, ẩn cửa sổ Mira lúc chụp, rồi hiện ảnh để bạn xem trước. Chọn **Đính kèm ảnh này**, nhập “Giúp tôi tìm lỗi trong màn hình này”, sau đó bấm **Gửi**. Ảnh tạm được xóa sau khi đọc; ảnh chỉ ở trong RAM cho đến khi gửi/bỏ. Cần chọn mô hình Ollama **có khả năng đọc ảnh**. Nếu dùng mô hình cloud và bạn đồng ý gửi, Ollama Cloud nhận ảnh này.
- Bật **◉ Cho Mira xem trạng thái PC** để hỏi từ app hoặc điện thoại: “Laptop đang sạc không?”, “Pin còn bao nhiêu?”. Mira đọc trực tiếp trạng thái nguồn/pin do Windows báo và trả lời ngay, không gọi mô hình cho câu hỏi pin đơn giản. Bảng trạng thái còn có RAM trống, dung lượng ổ hệ thống và số luồng CPU. Quyền mặc định tắt và mất khi đóng app; nếu Windows không báo được tình trạng pin, Mira nói là không xác định.
- Để Mira thao tác, bấm **🖱 Bật điều khiển máy** trong bảng bên phải hoặc mục công cụ. Quyền chỉ có trong phiên desktop Windows này và **mỗi hành động đều hỏi duyệt**. Gửi ảnh màn hình vừa chụp kèm yêu cầu cụ thể, ví dụ “Nhấp vào ô tìm kiếm rồi gõ tên tài liệu này”. Mira hiện hỗ trợ một cú nhấp chuột trái cho mỗi ảnh, gõ tối đa 500 ký tự, phím tắt thông dụng và mở Notepad/Máy tính/File Explorer. Sau khi nhấp hãy chụp ảnh mới để Mira kiểm tra tiếp; Mira không biết màn hình đã đổi ra sao nếu bạn chưa gửi ảnh mới. Bạn có thể tắt quyền bất cứ lúc nào; quyền không giữ qua lần mở ứng dụng tiếp theo.

Mira không âm thầm theo dõi màn hình hoặc nghe microphone. Telegram không được xem trạng thái hoặc màn hình máy. Trên trang điện thoại Tailscale, bạn có thể bật riêng quyền xem trạng thái PC, chụp từng ảnh màn hình hoặc đọc thư mục được chọn trong **Điện thoại & lịch nhắc** trên máy tính. Chat điện thoại không điều khiển chuột/bàn phím, sửa file hay chạy lệnh. Các trang web, ảnh và file có thể chứa hướng dẫn sai cho AI; hãy xem kỹ nội dung trước khi gửi.

## Các việc thường làm

| Việc | Cách dùng |
| --- | --- |
| Trò chuyện | Nhập ở **NHẮN MIRA**, bấm Gửi. Lỗi kết nối có nút **Thử gửi lại**. |
| Giữ nhiều cuộc trò chuyện | Bấm **+ Cuộc trò chuyện mới**; chọn lịch sử ở cột trái. Có thể đổi tên, xóa hoặc xuất cuộc trò chuyện hiện tại ra `.txt`. |
| Làm việc với code/file | Bấm **Mở tất cả công cụ → Chọn thư mục** rồi **＋ File** cạnh ô chat để điền đường dẫn. Mira chỉ đọc/tìm và đề xuất sửa file trong thư mục đó. Có thể bỏ quyền trong **Mô hình & cài đặt**. |
| Sửa file | Mira hiển thị diff đầy đủ. Chọn **Duyệt và ghi file** hoặc **Từ chối**. File cũ được sao lưu trước khi ghi. |
| Kiểm tra Python | Hỏi “Kiểm tra cú pháp `src/app.py`”. Mira phân tích cú pháp mà không chạy chương trình. |
| Chạy kiểm thử dự án | Bấm **▶ Kiểm thử** cạnh ô chat. Mira hiện chính xác lệnh Python unittest hoặc npm test và thư mục chạy; chỉ thực hiện sau khi bạn đồng ý. |
| Dạy dần | Bấm **Mở tất cả công cụ → Dạy Mira / bộ nhớ** để thêm, sửa hoặc xóa điều cần nhớ; mở **Bộ sở thích** để chỉnh quy tắc, thêm ví dụ “câu hỏi → câu trả lời mẫu”, hoặc xuất/nhập JSON. |
| Chọn tính cách | Bật/tắt **✦ Mira hoạt bát** ngay phía trên hội thoại. Trong **Mô hình & cài đặt**, bạn có thể thêm vài dòng mô tả cách nói chuyện bạn thích rồi bấm **Lưu**. |
| Nghe Mira trả lời | Sau một câu trả lời, bấm **🔊 Nghe**; bấm lại để dừng. Trong **Mô hình & cài đặt**, có thể bật tự đọc sau mỗi câu trả lời. Windows dùng giọng đã cài trên máy; chất lượng tiếng Việt phụ thuộc vào giọng có sẵn. |
| Tạo nhân vật Mira | Nhấp vào hình Mira ở góc trên của cuộc trò chuyện, chọn màu tóc hoặc tải ảnh PNG nhân vật do bạn tạo; nhân vật 2D chớp mắt và đổi nét theo trạng thái trả lời/đọc. |
| Hỏi về ảnh màn hình | Tự chụp/lưu ảnh PNG hoặc JPEG, bấm **＋ Ảnh** cạnh ô chat, chọn file, rồi gửi. Chạy `ollama pull qwen3-vl:4b` rồi chọn mô hình này trong **Mô hình & cài đặt**; `qwen3:4b` mặc định chỉ dùng cho văn bản. Ảnh chỉ gửi trong lượt đó, lịch sử lưu tên file chứ không lưu ảnh. |
| Trò chuyện từ điện thoại | Bấm **Điện thoại & lịch nhắc** ở thanh bên, làm theo hướng dẫn ghép nối phía dưới. |
| Đặt lịch nhắc | Bấm **Lịch nhắc** trong mục điện thoại; nhập ngày giờ hoặc nhờ Mira điền bản nháp, kiểm tra rồi bấm **Lưu lịch**. |
| Nhận nhắc qua Telegram | Tạo bot riêng bằng @BotFather, mở **Điện thoại & lịch nhắc → Nhắc qua Telegram**, ghép nối bằng mã. Bấm **Lưu lịch** trên bot để xác nhận. |

Nếu bạn đã dùng bản đầu, lịch sử trong `conversation.json` sẽ được nhập tự động vào mục **Cuộc trò chuyện trước đây**. Bộ nhớ cũ vẫn được giữ.

## Kết nối điện thoại, lịch nhắc và điều khiển máy tính

### Telegram: chat và nhắc lịch ngay trong ứng dụng điện thoại

Đây là cách tiện nhất nếu bạn đã dùng Telegram; Bot API không yêu cầu trả phí. Telegram dùng mạng của điện thoại để hiển thị thông báo. **Máy tính vẫn phải bật, có mạng, và Mira phải chạy** để trả lời và gửi nhắc đúng giờ. Không cần Tailscale hoặc mở cổng router cho cách này.

1. Trong Telegram, mở [@BotFather](https://t.me/BotFather), gửi `/newbot` và làm theo hướng dẫn để lấy **token bot riêng**. Không gửi token cho ai. Chỉ dùng bot trong cuộc trò chuyện riêng, tránh thêm vào nhóm.
2. Trên máy tính, giải nén bản Mira mới, chạy Mira → **📱 Điện thoại & lịch nhắc → Nhắc qua Telegram**. Dán token, bấm **Bật / tạo mã mới**, chờ dòng **Telegram sẵn sàng**. Nếu muốn tự kết nối sau khi mở Mira, đánh dấu lưu token trong hồ sơ Windows; nếu bỏ chọn, Mira chỉ giữ token trong phiên chạy và bạn phải nhập lại lần sau.
3. Trên điện thoại, mở bot bạn vừa tạo, gửi `/start 12345678` với **mã 8 chữ số hiển thị trong Mira**, không phải dãy ví dụ này. Mã có hiệu lực 5 phút và chỉ ghép nối một lần; tài khoản Telegram khác không thể dùng bot để đọc chat hoặc điều khiển Mira khi chưa có mã. Có thể thu hồi quyền trong cửa sổ này.
4. Gửi tin nhắn bình thường để chat. Để đặt lịch **không cần AI và không tốn lượt cloud**, gửi `/nhac YYYY-MM-DD HH:MM | Việc cần làm`, chẳng hạn thay `YYYY-MM-DD` bằng ngày mai. Nếu muốn Mira hiểu lời tự nhiên, gửi `/nhac Nhắc tôi ngày mai lúc 9 giờ gọi mẹ`; việc này dùng mô hình Ollama bạn đã chọn, có thể dùng lượt Free nếu là cloud. Mira gửi **bản nháp** và hai nút; kiểm tra ngày giờ rồi bấm **✅ Lưu lịch**. Bot sẽ nhắn `🔔` khi đến giờ nếu Mira còn chạy.

Lệnh thêm: `/lich` xem lịch sắp tới, `/xoa <8 ký tự đầu>` xóa lịch trong Mira, `/muigio +7` chọn múi giờ, `/help` xem hướng dẫn. Bot chỉ nhận tin nhắn từ đúng cuộc trò chuyện Telegram đã ghép nối; lịch chung với Mira trên máy tính và trang điện thoại Tailscale. Nếu máy tính ngủ, tắt hoặc mất mạng, Telegram **không báo đúng giờ**. Mira sẽ thử gửi lại trong vòng 24 giờ sau thời điểm lịch nếu máy hoạt động lại. Hãy bật thông báo cho Telegram trên điện thoại; thông báo Telegram có thể bị chế độ im lặng hoặc Không làm phiền chặn.

**Báo thức trong ứng dụng Đồng hồ:** Telegram bot không có quyền tạo báo thức hệ thống trên Android/iPhone. Để điện thoại báo đúng giờ khi máy tính tắt, nhập lịch `.ics` vào ứng dụng Lịch hỗ trợ thông báo, hoặc tự đặt báo thức trong ứng dụng Đồng hồ. Một ứng dụng Android riêng được cấp quyền báo thức có thể tạo báo thức trên Android; Mira hiện chưa có ứng dụng điện thoại như vậy.

**Chat với Mira trên điện thoại (Tailscale Personal miễn phí):**

1. Cài [Tailscale](https://tailscale.com/download) trên máy tính Windows và điện thoại Android/iPhone; đăng nhập cùng tài khoản trên cả hai thiết bị. Mira và Ollama cần đang mở trên máy tính; nếu máy yếu, có thể chọn mô hình Ollama Cloud đã đồng ý sử dụng trong Mira.
2. Trên máy tính mở Mira → **📱 Điện thoại & lịch nhắc** → **Bật / tạo mã mới**. Ghi lại mã 8 chữ số, hiệu lực 5 phút và chỉ dùng một lần.
3. Mở PowerShell trên máy tính, chạy `tailscale serve --bg 8765`. Tailscale sẽ in ra một địa chỉ `https://...ts.net`; mở địa chỉ đó bằng trình duyệt điện thoại và nhập mã. Nếu chưa hiện địa chỉ, chạy `tailscale serve status`. **Dùng Serve, không dùng Funnel**, vì Funnel công khai ra Internet.
4. Trên điện thoại có các tab **Trò chuyện**, **Lịch nhắc** và **Điều khiển**. Trong tab Trò chuyện, chạm **Gửi tin nhắn** hoặc dùng Enter; Shift+Enter xuống dòng. Chat điện thoại được lưu riêng trong `%LOCALAPPDATA%\Mira\phone_conversation.json`. Mặc định điện thoại không có quyền đọc thông tin PC. Trong cửa sổ Mira trên máy tính, bạn có thể bật **từng quyền** cho phiên hiện tại: xem pin/trạng thái PC, chụp một ảnh màn hình từ điện thoại, hoặc đọc file văn bản trong thư mục đã chọn. Khi chụp từ điện thoại, ảnh hiện để xem trước và hết hạn sau 2 phút; chỉ bấm **Gửi tin nhắn** nếu bạn muốn chuyển ảnh cho AI, đặc biệt khi dùng mô hình cloud. Để đọc file, chọn thư mục trên máy tính trước; quyền này chỉ cho đọc/tìm, không cho sửa. Không có quyền điều khiển máy hoặc chạy lệnh qua AI điện thoại. Để ngắt, bấm **Ngắt kết nối** trong Mira hoặc đóng Mira; muốn tắt luôn địa chỉ Serve, xem hướng dẫn của Tailscale.

Mã ghép nối chỉ hiển thị trên máy tính. Kết nối điện thoại sử dụng HTTPS của Tailscale Serve, xác minh danh tính do Tailscale chuyển tới, phiên ghép nối có hạn 12 giờ. Tailscale Personal miễn phí có điều kiện sử dụng và giới hạn của nhà cung cấp; không cần mở cổng router hay đăng ký tên miền. Nếu dùng thiết bị được gắn tag của Tailscale, header danh tính không có và Mira sẽ từ chối; hãy dùng điện thoại đăng nhập cá nhân.

**Lịch nhắc:** Trong Mira trên máy tính chọn **Lịch nhắc**, hoặc trên điện thoại mở tab cùng tên. Có thể tự nhập ngày giờ hoặc viết “Nhắc tôi ngày mai lúc 9 giờ gọi mẹ” rồi bấm **Mira điền biểu mẫu**. Mira chỉ gợi ý; **bạn kiểm tra và bấm Lưu** để tạo một lịch nhắc. Khi Mira đang mở, máy tính báo bằng cửa sổ ở thời điểm đã chọn; nếu bot Telegram đã ghép nối và đang chạy, Mira cũng gửi tin nhắn Telegram. Để điện thoại nhắc cả khi máy tính tắt, bấm **Thêm vào lịch điện thoại (.ics)** và nhập tệp đó vào ứng dụng Lịch có hỗ trợ tệp `.ics` và báo thức; đây là một lần nhập thủ công. Sửa hoặc xóa lịch trong Mira không tự cập nhật lịch đã nhập trên điện thoại. Nếu dùng iPhone/Android, cách mở tệp và quyền thông báo tùy ứng dụng lịch bạn chọn. Chưa có lịch lặp lại hoặc đồng bộ Google/Apple Calendar tự động.

**Điều khiển màn hình máy tính từ xa:** Cài [Chrome Remote Desktop](https://remotedesktop.google.com/access) trên máy tính, bật **Truy cập từ xa** và đặt mã PIN theo hướng dẫn của Google. Trên điện thoại mở ứng dụng Chrome Remote Desktop hoặc tab **Điều khiển** trong trang Mira, đăng nhập cùng tài khoản Google và chọn máy. Đây là quyền điều khiển màn hình bằng tay của bạn, tách khỏi quyền chat của Mira. Máy tính phải đang bật, không ngủ và có mạng; tính năng này cần tài khoản Google và chưa được tự cài/bật trên máy của bạn.

## Bộ dữ liệu sở thích miễn phí

Mira có sẵn `mira/preferences_starter.json` gồm các quy tắc trả lời và ví dụ cho trò chuyện, dịch tự nhiên, hỗ trợ code, giao diện dễ đọc và xử lý lỗi máy tính. Lần chạy đầu, ứng dụng chép bộ mẫu vào `%LOCALAPPDATA%\Mira\preferences.json`; **từ đó chỉ sửa bản của bạn**. Bấm **Mở tất cả công cụ → Dạy Mira / bộ nhớ → Bộ sở thích** để xem, thêm, sửa, xóa, xuất hoặc nhập bộ JSON. Bạn cũng có thể khôi phục bộ mẫu nếu muốn; việc cập nhật file mẫu không tự ghi đè bộ sở thích đã chỉnh của bạn.

Mira chỉ chọn **tối đa hai ví dụ liên quan** cho mỗi câu hỏi và giới hạn số ghi nhớ gửi vào mô hình để giữ tốc độ. Các ví dụ giúp định hướng cách trả lời; chúng **không huấn luyện lại trọng số**. Dữ liệu sở thích lưu trên máy, không cần tài khoản hay API trả phí khi dùng mô hình cục bộ đã tải. Khi chọn mô hình cloud, Mira gửi phần sở thích/ghi nhớ liên quan cùng yêu cầu đến Ollama Cloud sau khi bạn đồng ý.

### Chế độ Mira hoạt bát

Mira trả lời ngắn khi trò chuyện đơn giản, đi vào chi tiết khi bạn cần làm việc, và mặc định xưng **mình-bạn** nếu bạn chưa chọn cách xưng hô khác. Chế độ **✦ Mira hoạt bát** cho phép thêm chút dí dỏm trong chuyện đời thường mà không chèn trò đùa vào việc nghiêm túc; tắt để dùng giọng điềm tĩnh hơn. Giọng hội thoại mới áp dụng ngay cho tin nhắn gửi sau khi cài bản cập nhật, kể cả khi bạn đã có bộ sở thích riêng.

Để Mira nói đúng gu, mở **Mô hình & cài đặt → Cách xưng hô, độ dài, mức độ hài hước** và nhập, ví dụ: “Xưng mình-bạn, thường trả lời 2–4 câu; bỏ chào đầu mỗi lượt; không dùng lời khen xã giao; giải thích kỹ khi tôi hỏi về code.” Bấm **Lưu**. Trong **Bộ sở thích**, bạn cũng có thể thêm vài cặp **câu hỏi → câu trả lời mẫu** do chính bạn viết; nhờ vậy Mira có ví dụ phù hợp khi gặp chủ đề tương tự. Thay đổi áp dụng từ tin nhắn sau đó, không cần huấn luyện mô hình hoặc trả tiền. Lựa chọn và ghi chú tính cách nằm trong `%LOCALAPPDATA%\Mira\settings.json` qua các lần nâng cấp.

Đây là một tính cách hội thoại lấy cảm hứng từ AI VTuber, không phải bản sao mô hình, giọng nói hay nhân vật của Neuro-sama. Mira có nhân vật anime 2D vẽ bằng Tkinter, chớp mắt và đổi nét khi tạo chữ/đọc thành tiếng; nhấp vào hình để chọn một trong ba bảng màu hoặc nhập ảnh PNG của riêng bạn. Trên trang điện thoại, Mira có hình anime tương ứng và hiển thị ảnh PNG riêng nếu bạn đã chọn. Ảnh PNG tùy chỉnh lưu trong `%LOCALAPPDATA%\Mira\mira_character.png`, không tải lên dịch vụ tạo hình; ảnh được gửi tới điện thoại chỉ qua phiên riêng Tailscale đã ghép nối. Avatar PNG tùy chỉnh là ảnh tĩnh; nhân vật vẽ sẵn có chuyển động mắt/miệng. Đây chưa phải 3D VRM/Live2D hoặc nhận lời nói từ microphone. Mira không xem màn hình liên tục, chơi game hay tự phát tin khi bạn không nhắn. Các thao tác file trên desktop vẫn cần quyền và xác nhận như trước.

## Quyền truy cập và giới hạn

- Mira kết nối với ứng dụng Ollama qua `127.0.0.1:11434`. Mô hình cục bộ xử lý trên máy; với mô hình cloud (`:cloud` hoặc `-cloud`), Ollama chuyển yêu cầu qua Internet để xử lý trên máy chủ. Mira hỏi đồng ý trước lượt chat cloud đầu tiên và cho phép thu hồi. Tin nhắn, lịch sử gần đây, ghi nhớ/sở thích được chọn, ảnh bạn đính kèm và nội dung file công cụ đọc được có thể vào yêu cầu đó. Không tự động gửi cả thư mục. Nếu tạo alias cloud với tên tùy ý không có đuôi cloud, Mira không thể tự nhận ra alias đó; hãy tránh dùng alias như vậy khi cần bảo vệ dữ liệu.
- Chỉ các file trong thư mục do bạn chọn mới được đọc/tìm/sửa. Mira từ chối đường dẫn ra ngoài, symlink, một số file thường chứa thông tin đăng nhập và thư mục sinh tự động (`.git`, `node_modules`, `.venv`...). File đọc tối đa 64 KiB, file sửa tối đa 128 KiB, văn bản UTF-8. Mỗi lần ghi đều phải được bạn duyệt.
- Mira không tự chạy lệnh do mô hình đề xuất. Nút **Chạy kiểm thử** chỉ chạy lệnh đã hiển thị sau khi bạn xác nhận; kiểm thử có thể thực thi code của dự án. Khi bạn bật quyền desktop trong một phiên Windows, Mira có thể đề nghị nhấp chuột, gõ chữ hoặc phím tắt; mỗi hành động cần bạn duyệt. Ứng dụng không đọc màn hình liên tục hay nghe microphone. Để Mira xem ảnh, bạn phải chọn ảnh hoặc tự chụp rồi duyệt ảnh trước khi gửi, và dùng mô hình có khả năng đọc ảnh. Trang điện thoại chỉ có thể chụp từng ảnh nếu bạn bật quyền tại máy tính; từng ảnh phải được xem trước rồi gửi bằng tay từ điện thoại. Code và lời khuyên do AI tạo ra có thể sai; hãy xem diff và thao tác trước khi duyệt.
- Giọng đọc chỉ hoạt động trên Windows có PowerShell và giọng System.Speech cài sẵn. Văn bản trả lời được đưa vào bộ tổng hợp giọng nói cục bộ; mã code, liên kết và đoạn quá dài được lược bớt khi đọc. Ứng dụng không tự bật micro và không dùng dịch vụ TTS trả phí.
- Giao diện điện thoại chỉ mở khi bạn bật trong Mira, lắng nghe `127.0.0.1:8765` và cần Tailscale Serve, mã ghép nối một lần, cookie phiên cùng xác minh CSRF. Nếu đã ghép nối, người dùng cầm điện thoại hoặc tài khoản có quyền đăng nhập thiết bị đó có thể xem chat điện thoại và lịch nhắc. Không chia sẻ mã, tài khoản Tailscale hoặc thiết bị đã ghép nối.
- Quyền xem trạng thái PC, chụp màn hình từ điện thoại và đọc thư mục chỉ có hiệu lực trong phiên Mira hiện tại; tất cả mặc định tắt. Ảnh màn hình và mã xem trước ở trong RAM, không lưu vào lịch sử ảnh, hết hạn trong 2 phút và chỉ gửi trong lượt chat nếu bạn bấm Gửi. Khi dùng mô hình Ollama Cloud đã đồng ý, trạng thái PC, ảnh hoặc nội dung file được đọc có thể đến Ollama Cloud. Thay thư mục sẽ thu hồi quyền đọc thư mục từ điện thoại. Các file khác ngoài thư mục chọn, file nhị phân, nội dung dài, thư mục hệ thống và file nhạy cảm được lọc/giới hạn bởi Workspace. Mira không có quyền “đọc mọi thứ” trên máy và không có truy cập quản trị hệ điều hành.
- Bot Telegram chỉ chạy khi bạn bật hoặc đã chọn tự bật; nhận tin nhắn qua long polling, không dùng webhook công khai. Bot chỉ chat và đặt lịch, không có quyền sửa file/chạy lệnh từ Telegram. Nếu chọn ghi nhớ token, Mira lưu token trong hồ sơ người dùng trên máy tính dưới `%LOCALAPPDATA%\Mira\telegram_credentials.json`; giữ thư mục này riêng tư, thu hồi token trong @BotFather nếu bị lộ. Lịch đã lưu trong Mira có thể vẫn ở đó sau khi bạn thu hồi bot.
- Cài đặt, hội thoại, bộ nhớ và bản sao file cũ nằm ở `%LOCALAPPDATA%\Mira` trên Windows (hoặc `~/.local/share/Mira` trên Linux); không có trong ZIP hay repo. Bản sao nằm trong `backups` và có thể được chép về vị trí cũ để phục hồi.

## Dành cho người phát triển

```bash
python run_mira.py
python -m unittest discover -s tests -v
```

`mira/gui.py` chứa giao diện; `mira/telegram_bot.py` kết nối Bot API qua long polling; `mira/mobile_server.py` và `mira/phone.html` phục vụ giao diện điện thoại qua loopback; `mira/reminders.py` lưu lịch và xuất `.ics`; `mira/agent.py` gọi Ollama và giới hạn công cụ; `mira/workspace.py` kiểm tra đường dẫn, diff và sao lưu; `mira/storage.py` lưu dữ liệu cục bộ; `mira/preferences.py` chọn sở thích theo ngữ cảnh. Không yêu cầu thư viện Python ngoài standard library cho tính năng hiện có.
