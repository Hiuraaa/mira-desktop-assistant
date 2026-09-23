# Mira — trợ lý AI cá nhân trên máy tính

Mira là ứng dụng desktop dành cho Windows, trò chuyện bằng tiếng Việt qua Ollama. Bạn có thể dùng mô hình trên máy hoặc chọn mô hình Ollama Cloud cho máy yếu. Mira giúp giải thích, viết code, tìm/đọc file, kiểm tra cú pháp Python và đề xuất sửa file trong thư mục bạn chọn. Tên gọi và cách xưng hô của Mira có thể chỉnh trong **Mô hình & cài đặt**.

## Chạy Mira trên Windows

1. Cài [Python 3.11+](https://www.python.org/downloads/) và chọn **Add python.exe to PATH** trong trình cài đặt.
2. Cài [Ollama cho Windows](https://ollama.com/download/windows) và mở Ollama.
3. Nếu dùng AI trên máy, mở PowerShell, chạy `ollama pull qwen3:4b` và đợi tải xong. Nếu máy yếu, bỏ qua bước tải mô hình lớn và làm theo mục **AI cloud cho máy yếu** bên dưới.
4. Giải nén ZIP, nhấn đúp **`start_windows.bat`**. Không cần `pip install` cho bản cơ bản.
5. Màn hình mở thẳng vào chat: ô **NHẮN MIRA** màu sáng nằm ngay dưới vùng hội thoại. Nhập câu hỏi rồi bấm **Gửi** hoặc Enter. **Shift+Enter** xuống dòng. Thanh trạng thái phía trên cho biết Ollama đã sẵn sàng chưa; bấm **Cách cài** nếu cần.

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

Trong thanh bên chọn **🚀 Mô hình mạnh & tốc độ**. Bạn có thể bấm **Tải 9B** để cài `qwen3.5:9b` miễn phí bằng Ollama (khoảng 6,6 GB dữ liệu tải), hoặc **Tải 4B** cho `qwen3.5:4b` (khoảng 3,4 GB). Sau khi tải, Mira tự chọn mô hình đó. Cả hai nhận ảnh và có khả năng gọi công cụ. Nếu muốn cài thủ công, dùng `ollama pull qwen3.5:9b` trong PowerShell rồi chọn trong **Mô hình & cài đặt**.

Nút **Đo tốc độ** cho các mô hình đã cài tạo một câu ngắn trên chính máy bạn, hiển thị token/giây, thời gian tải mô hình và tổng thời gian. Đây chỉ là phép đo một lượt ngắn, không đo chất lượng câu trả lời. Mô hình 9B có thể hiểu và làm việc phức tạp tốt hơn nhưng **không bảo đảm nhanh hơn** 4B; nếu vượt dung lượng RAM/VRAM thì sẽ chậm rõ rệt. Chọn mô hình theo kết quả đo và mức độ hữu ích của câu trả lời thực tế.

**Suy luận sâu** trong cửa sổ này cho phép mô hình có hỗ trợ suy luận dành thêm thời gian cho việc khó. Chế độ này tắt mặc định để chat nhanh; bật lên có thể khiến Mira chờ lâu trước khi hiện chữ đầu tiên. Chế độ **Ưu tiên tốc độ** và **Suy luận sâu** được lưu riêng.

## Các việc thường làm

| Việc | Cách dùng |
| --- | --- |
| Trò chuyện | Nhập ở **NHẮN MIRA**, bấm Gửi. Lỗi kết nối có nút **Thử gửi lại**. |
| Giữ nhiều cuộc trò chuyện | Bấm **+ Cuộc trò chuyện mới**; chọn lịch sử ở cột trái. Có thể đổi tên, xóa hoặc xuất cuộc trò chuyện hiện tại ra `.txt`. |
| Làm việc với code/file | Bấm **Chọn thư mục làm việc** rồi **Chọn file** để điền đường dẫn vào ô chat. Mira chỉ đọc/tìm và đề xuất sửa file trong thư mục đó. Có thể bỏ quyền trong **Mô hình & cài đặt**. |
| Sửa file | Mira hiển thị diff đầy đủ. Chọn **Duyệt và ghi file** hoặc **Từ chối**. File cũ được sao lưu trước khi ghi. |
| Kiểm tra Python | Hỏi “Kiểm tra cú pháp `src/app.py`”. Mira phân tích cú pháp mà không chạy chương trình. |
| Chạy kiểm thử dự án | Bấm **Chạy kiểm thử**. Mira hiện chính xác lệnh Python unittest hoặc npm test và thư mục chạy; chỉ thực hiện sau khi bạn đồng ý. |
| Dạy dần | Bấm **Dạy Mira / bộ nhớ** để thêm, sửa hoặc xóa điều cần nhớ; mở **Bộ sở thích** để chỉnh quy tắc, thêm ví dụ “câu hỏi → câu trả lời mẫu”, hoặc xuất/nhập JSON. |
| Chọn tính cách | Bật/tắt **✦ Mira hoạt bát** ngay phía trên hội thoại. Trong **Mô hình & cài đặt**, bạn có thể thêm vài dòng mô tả cách nói chuyện bạn thích rồi bấm **Lưu**. |
| Nghe Mira trả lời | Sau một câu trả lời, bấm **🔊 Nghe**; bấm lại để dừng. Trong **Mô hình & cài đặt**, có thể bật tự đọc sau mỗi câu trả lời. Windows dùng giọng đã cài trên máy; chất lượng tiếng Việt phụ thuộc vào giọng có sẵn. |
| Hỏi về ảnh màn hình | Tự chụp/lưu ảnh PNG hoặc JPEG, bấm **Đính kèm ảnh**, chọn file, rồi gửi. Chạy `ollama pull qwen3-vl:4b` rồi chọn mô hình này trong **Mô hình & cài đặt**; `qwen3:4b` mặc định chỉ dùng cho văn bản. Ảnh chỉ gửi trong lượt đó, lịch sử lưu tên file chứ không lưu ảnh. |
| Trò chuyện từ điện thoại | Bấm **📱 Điện thoại & lịch nhắc** ở thanh bên, làm theo hướng dẫn ghép nối phía dưới. |
| Đặt lịch nhắc | Bấm **Lịch nhắc** trong mục điện thoại; nhập ngày giờ hoặc nhờ Mira điền bản nháp, kiểm tra rồi bấm **Lưu lịch**. |

Nếu bạn đã dùng bản đầu, lịch sử trong `conversation.json` sẽ được nhập tự động vào mục **Cuộc trò chuyện trước đây**. Bộ nhớ cũ vẫn được giữ.

## Kết nối điện thoại, lịch nhắc và điều khiển máy tính

**Chat với Mira trên điện thoại (Tailscale Personal miễn phí):**

1. Cài [Tailscale](https://tailscale.com/download) trên máy tính Windows và điện thoại Android/iPhone; đăng nhập cùng tài khoản trên cả hai thiết bị. Mira và Ollama cần đang mở trên máy tính; nếu máy yếu, có thể chọn mô hình Ollama Cloud đã đồng ý sử dụng trong Mira.
2. Trên máy tính mở Mira → **📱 Điện thoại & lịch nhắc** → **Bật / tạo mã mới**. Ghi lại mã 8 chữ số, hiệu lực 5 phút và chỉ dùng một lần.
3. Mở PowerShell trên máy tính, chạy `tailscale serve --bg 8765`. Tailscale sẽ in ra một địa chỉ `https://...ts.net`; mở địa chỉ đó bằng trình duyệt điện thoại và nhập mã. Nếu chưa hiện địa chỉ, chạy `tailscale serve status`. **Dùng Serve, không dùng Funnel**, vì Funnel công khai ra Internet.
4. Trên điện thoại có thể chat và mở tab **Lịch nhắc**. Chat điện thoại được lưu riêng trong `%LOCALAPPDATA%\Mira\phone_conversation.json`. Trang điện thoại không có quyền xem/sửa file hoặc chạy lệnh trong máy tính; mô hình cloud vẫn dùng lựa chọn đồng ý đã đặt trên máy tính. Để ngắt, bấm **Ngắt kết nối** trong Mira hoặc đóng Mira; muốn tắt luôn địa chỉ Serve, chạy `tailscale serve --bg 8765 off` trên máy tính.

Mã ghép nối chỉ hiển thị trên máy tính. Kết nối điện thoại sử dụng HTTPS của Tailscale Serve, xác minh danh tính do Tailscale chuyển tới, phiên ghép nối có hạn 12 giờ. Tailscale Personal miễn phí có điều kiện sử dụng và giới hạn của nhà cung cấp; không cần mở cổng router hay đăng ký tên miền. Nếu dùng thiết bị được gắn tag của Tailscale, header danh tính không có và Mira sẽ từ chối; hãy dùng điện thoại đăng nhập cá nhân.

**Lịch nhắc:** Trong Mira trên máy tính chọn **Lịch nhắc**, hoặc trên điện thoại mở tab cùng tên. Có thể tự nhập ngày giờ hoặc viết “Nhắc tôi ngày mai lúc 9 giờ gọi mẹ” rồi bấm **Mira điền biểu mẫu**. Mira chỉ gợi ý; **bạn kiểm tra và bấm Lưu** để tạo một lịch nhắc. Khi Mira đang mở, máy tính báo bằng cửa sổ ở thời điểm đã chọn. Để điện thoại nhắc cả khi máy tính tắt, bấm **Thêm vào lịch điện thoại (.ics)** và nhập tệp đó vào ứng dụng Lịch có hỗ trợ tệp `.ics` và báo thức; đây là một lần nhập thủ công. Sửa hoặc xóa lịch trong Mira không tự cập nhật lịch đã nhập trên điện thoại. Nếu dùng iPhone/Android, cách mở tệp và quyền thông báo tùy ứng dụng lịch bạn chọn. Chưa có lịch lặp lại hoặc đồng bộ Google/Apple Calendar tự động.

**Điều khiển màn hình máy tính từ xa:** Cài [Chrome Remote Desktop](https://remotedesktop.google.com/access) trên máy tính, bật **Truy cập từ xa** và đặt mã PIN theo hướng dẫn của Google. Trên điện thoại mở ứng dụng Chrome Remote Desktop hoặc liên kết **Điều khiển toàn bộ máy tính** trong tab Lịch nhắc, đăng nhập cùng tài khoản Google và chọn máy. Đây là quyền điều khiển màn hình bằng tay của bạn, tách khỏi quyền chat của Mira. Máy tính phải đang bật, không ngủ và có mạng; tính năng này cần tài khoản Google và chưa được tự cài/bật trên máy của bạn.

## Bộ dữ liệu sở thích miễn phí

Mira có sẵn `mira/preferences_starter.json` gồm các quy tắc trả lời và ví dụ cho dịch tự nhiên, hỗ trợ code, giao diện dễ đọc và xử lý lỗi máy tính. Lần chạy đầu, ứng dụng chép bộ mẫu vào `%LOCALAPPDATA%\Mira\preferences.json`; **từ đó chỉ sửa bản của bạn**. Bấm **Dạy Mira / bộ nhớ → Bộ sở thích** để xem, thêm, sửa, xóa, xuất hoặc nhập bộ JSON. Bạn cũng có thể khôi phục bộ mẫu nếu muốn.

Mira chỉ chọn **tối đa hai ví dụ liên quan** cho mỗi câu hỏi và giới hạn số ghi nhớ gửi vào mô hình để giữ tốc độ. Các ví dụ giúp định hướng cách trả lời; chúng **không huấn luyện lại trọng số**. Dữ liệu sở thích lưu trên máy, không cần tài khoản hay API trả phí khi dùng mô hình cục bộ đã tải. Khi chọn mô hình cloud, Mira gửi phần sở thích/ghi nhớ liên quan cùng yêu cầu đến Ollama Cloud sau khi bạn đồng ý.

### Chế độ Mira hoạt bát

Chế độ này được bật mặc định sau khi cập nhật; bấm **✦ Mira hoạt bát** để chuyển nhanh sang giọng trợ lý thông thường. Mira trò chuyện tò mò, ứng biến và đôi lúc đùa nhẹ, nhưng vẫn đi thẳng vào việc và giữ thái độ nghiêm túc khi cần. Bạn có thể nhập sở thích riêng trong **Mô hình & cài đặt** và chỉnh các ví dụ trong **Bộ sở thích**; thay đổi chỉ áp dụng cho những tin nhắn gửi sau đó. Lựa chọn và ghi chú tính cách được giữ trong `%LOCALAPPDATA%\Mira\settings.json` qua các lần nâng cấp.

Đây là một tính cách hội thoại lấy cảm hứng từ AI VTuber, không phải bản sao mô hình, giọng nói hay nhân vật của Neuro-sama. Mira có gương mặt tối giản riêng, đổi nét khi đang tạo chữ/đọc thành tiếng; giọng đọc tùy chọn dùng giọng Windows trên máy. Mira chưa nhận lời nói từ microphone, xem màn hình liên tục, chơi game hay tự phát tin khi bạn không nhắn. Các thao tác file vẫn cần quyền và xác nhận như trước.

## Quyền truy cập và giới hạn

- Mira kết nối với ứng dụng Ollama qua `127.0.0.1:11434`. Mô hình cục bộ xử lý trên máy; với mô hình cloud (`:cloud` hoặc `-cloud`), Ollama chuyển yêu cầu qua Internet để xử lý trên máy chủ. Mira hỏi đồng ý trước lượt chat cloud đầu tiên và cho phép thu hồi. Tin nhắn, lịch sử gần đây, ghi nhớ/sở thích được chọn, ảnh bạn đính kèm và nội dung file công cụ đọc được có thể vào yêu cầu đó. Không tự động gửi cả thư mục. Nếu tạo alias cloud với tên tùy ý không có đuôi cloud, Mira không thể tự nhận ra alias đó; hãy tránh dùng alias như vậy khi cần bảo vệ dữ liệu.
- Chỉ các file trong thư mục do bạn chọn mới được đọc/tìm/sửa. Mira từ chối đường dẫn ra ngoài, symlink, một số file thường chứa thông tin đăng nhập và thư mục sinh tự động (`.git`, `node_modules`, `.venv`...). File đọc tối đa 64 KiB, file sửa tối đa 128 KiB, văn bản UTF-8. Mỗi lần ghi đều phải được bạn duyệt.
- Mira không tự chạy lệnh do mô hình đề xuất. Nút **Chạy kiểm thử** chỉ chạy lệnh đã hiển thị sau khi bạn xác nhận; kiểm thử có thể thực thi code của dự án. Ứng dụng chưa điều khiển chuột, đọc màn hình liên tục hay nghe microphone. Để Mira xem ảnh, bạn cần chọn ảnh thủ công và dùng mô hình có hỗ trợ ảnh. Code và lời khuyên do AI tạo ra có thể sai; hãy xem diff trước khi ghi.
- Giọng đọc chỉ hoạt động trên Windows có PowerShell và giọng System.Speech cài sẵn. Văn bản trả lời được đưa vào bộ tổng hợp giọng nói cục bộ; mã code, liên kết và đoạn quá dài được lược bớt khi đọc. Ứng dụng không tự bật micro và không dùng dịch vụ TTS trả phí.
- Giao diện điện thoại chỉ mở khi bạn bật trong Mira, lắng nghe `127.0.0.1:8765` và cần Tailscale Serve, mã ghép nối một lần, cookie phiên cùng xác minh CSRF. Nếu đã ghép nối, người dùng cầm điện thoại hoặc tài khoản có quyền đăng nhập thiết bị đó có thể xem chat điện thoại và lịch nhắc. Không chia sẻ mã, tài khoản Tailscale hoặc thiết bị đã ghép nối.
- Cài đặt, hội thoại, bộ nhớ và bản sao file cũ nằm ở `%LOCALAPPDATA%\Mira` trên Windows (hoặc `~/.local/share/Mira` trên Linux); không có trong ZIP hay repo. Bản sao nằm trong `backups` và có thể được chép về vị trí cũ để phục hồi.

## Dành cho người phát triển

```bash
python run_mira.py
python -m unittest discover -s tests -v
```

`mira/gui.py` chứa giao diện; `mira/mobile_server.py` và `mira/phone.html` phục vụ giao diện điện thoại qua loopback; `mira/reminders.py` lưu lịch và xuất `.ics`; `mira/agent.py` gọi Ollama và giới hạn công cụ; `mira/workspace.py` kiểm tra đường dẫn, diff và sao lưu; `mira/storage.py` lưu dữ liệu cục bộ; `mira/preferences.py` chọn sở thích theo ngữ cảnh. Không yêu cầu thư viện Python ngoài standard library cho tính năng hiện có.
