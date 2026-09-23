# Mira — trợ lý AI cá nhân trên máy tính

Mira là ứng dụng desktop dành cho Windows, trò chuyện bằng tiếng Việt qua mô hình Ollama chạy trên máy bạn. Bạn có thể nhờ Mira giải thích, viết code, tìm/đọc file, kiểm tra cú pháp Python và đề xuất sửa file trong thư mục bạn chọn. Tên gọi và cách xưng hô của Mira có thể chỉnh trong **Mô hình & cài đặt**.

## Chạy Mira trên Windows

1. Cài [Python 3.11+](https://www.python.org/downloads/) và chọn **Add python.exe to PATH** trong trình cài đặt.
2. Cài [Ollama cho Windows](https://ollama.com/download/windows) và mở Ollama.
3. Mở PowerShell, chạy `ollama pull qwen3:4b` và đợi tải xong. Chọn mô hình khác có hỗ trợ gọi công cụ nếu muốn.
4. Giải nén ZIP, nhấn đúp **`start_windows.bat`**. Không cần `pip install` cho bản cơ bản.
5. Màn hình mở thẳng vào chat: ô **NHẮN MIRA** màu sáng nằm ngay dưới vùng hội thoại. Nhập câu hỏi rồi bấm **Gửi** hoặc Enter. **Shift+Enter** xuống dòng. Thanh trạng thái phía trên cho biết Ollama đã sẵn sàng chưa; bấm **Cách cài** nếu cần.

Máy yếu có thể mất thời gian để tạo câu trả lời đầu tiên. Khi mô hình chưa được tải, Mira sẽ hiển thị hướng dẫn ngay trên màn hình. Nếu Python Launcher (`py`) không có, file `.bat` sẽ thử `python`.

### Nếu Mira trả lời chậm

- Bản này **hiển thị nội dung dần** ngay khi Ollama bắt đầu tạo chữ. Thời gian suy luận thật vẫn tùy CPU/GPU và RAM trên máy; lần đầu tải mô hình thường chậm hơn.
- Trong **Mô hình & cài đặt**, bật **Ưu tiên tốc độ** (mặc định). Mira gửi ít lịch sử và ví dụ phù hợp hơn, dùng ngữ cảnh gọn; những cuộc trò chuyện dài hoặc file code lớn có thể cần tắt chế độ này để giữ thêm ngữ cảnh.
- Muốn giảm tải thêm, chạy `ollama pull qwen3:1.7b`, mở **Mô hình & cài đặt**, chọn `qwen3:1.7b`. Mô hình nhỏ hơn thường nhanh hơn nhưng có thể kém chính xác khi sửa code phức tạp. `qwen3:1.7b` chỉ dùng văn bản, không nhìn ảnh; khi gửi ảnh hãy chọn mô hình vision như `qwen3-vl:4b`.
- Mira giữ mô hình sẵn trong Ollama trong khoảng **15 phút** giữa các yêu cầu để tránh tải lại; điều này có thể giữ RAM đang dùng. Đây là tham số `keep_alive`, không chạy Mira trên cloud.

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
| Hỏi về ảnh màn hình | Tự chụp/lưu ảnh PNG hoặc JPEG, bấm **Đính kèm ảnh**, chọn file, rồi gửi. Chạy `ollama pull qwen3-vl:4b` rồi chọn mô hình này trong **Mô hình & cài đặt**; `qwen3:4b` mặc định chỉ dùng cho văn bản. Ảnh chỉ gửi trong lượt đó, lịch sử lưu tên file chứ không lưu ảnh. |

Nếu bạn đã dùng bản đầu, lịch sử trong `conversation.json` sẽ được nhập tự động vào mục **Cuộc trò chuyện trước đây**. Bộ nhớ cũ vẫn được giữ.

## Bộ dữ liệu sở thích miễn phí

Mira có sẵn `mira/preferences_starter.json` gồm các quy tắc trả lời và ví dụ cho dịch tự nhiên, hỗ trợ code, giao diện dễ đọc và xử lý lỗi máy tính. Lần chạy đầu, ứng dụng chép bộ mẫu vào `%LOCALAPPDATA%\Mira\preferences.json`; **từ đó chỉ sửa bản của bạn**. Bấm **Dạy Mira / bộ nhớ → Bộ sở thích** để xem, thêm, sửa, xóa, xuất hoặc nhập bộ JSON. Bạn cũng có thể khôi phục bộ mẫu nếu muốn.

Mira chỉ chọn **tối đa hai ví dụ liên quan** cho mỗi câu hỏi và giới hạn số ghi nhớ gửi vào mô hình để giữ tốc độ. Các ví dụ giúp định hướng cách trả lời; chúng **không huấn luyện lại trọng số**. Mọi dữ liệu sở thích nằm trên máy và không cần tài khoản hay API trả phí khi dùng mô hình Ollama cục bộ đã tải. Nếu chọn mô hình cloud qua Ollama, chi phí và xử lý dữ liệu sẽ theo dịch vụ đó.

### Chế độ Mira hoạt bát

Chế độ này được bật mặc định sau khi cập nhật; bấm **✦ Mira hoạt bát** để chuyển nhanh sang giọng trợ lý thông thường. Mira trò chuyện tò mò, ứng biến và đôi lúc đùa nhẹ, nhưng vẫn đi thẳng vào việc và giữ thái độ nghiêm túc khi cần. Bạn có thể nhập sở thích riêng trong **Mô hình & cài đặt** và chỉnh các ví dụ trong **Bộ sở thích**; thay đổi chỉ áp dụng cho những tin nhắn gửi sau đó. Lựa chọn và ghi chú tính cách được giữ trong `%LOCALAPPDATA%\Mira\settings.json` qua các lần nâng cấp.

Đây là một tính cách hội thoại lấy cảm hứng từ AI VTuber, không phải bản sao mô hình, giọng nói hay nhân vật của Neuro-sama. Mira hiện là ứng dụng chat bằng chữ; chế độ này không thêm nghe/nói liên tục, avatar, chơi game hoặc tự phát tin khi bạn không nhắn. Các thao tác file vẫn cần quyền và xác nhận như trước.

## Quyền truy cập và giới hạn

- Mira kết nối với Ollama qua `127.0.0.1:11434`. Nội dung chat, bộ nhớ, những file được Mira đọc và ảnh bạn chủ động đính kèm sẽ được gửi tới mô hình đã chọn. Nếu chọn mô hình cloud trong Ollama, cách xử lý dữ liệu phụ thuộc dịch vụ mô hình đó.
- Chỉ các file trong thư mục do bạn chọn mới được đọc/tìm/sửa. Mira từ chối đường dẫn ra ngoài, symlink, một số file thường chứa thông tin đăng nhập và thư mục sinh tự động (`.git`, `node_modules`, `.venv`...). File đọc tối đa 64 KiB, file sửa tối đa 128 KiB, văn bản UTF-8. Mỗi lần ghi đều phải được bạn duyệt.
- Mira không tự chạy lệnh do mô hình đề xuất. Nút **Chạy kiểm thử** chỉ chạy lệnh đã hiển thị sau khi bạn xác nhận; kiểm thử có thể thực thi code của dự án. Ứng dụng chưa điều khiển chuột, đọc màn hình liên tục hay nghe microphone. Để Mira xem ảnh, bạn cần chọn ảnh thủ công và dùng mô hình có hỗ trợ ảnh. Code và lời khuyên do AI tạo ra có thể sai; hãy xem diff trước khi ghi.
- Cài đặt, hội thoại, bộ nhớ và bản sao file cũ nằm ở `%LOCALAPPDATA%\Mira` trên Windows (hoặc `~/.local/share/Mira` trên Linux); không có trong ZIP hay repo. Bản sao nằm trong `backups` và có thể được chép về vị trí cũ để phục hồi.

## Dành cho người phát triển

```bash
python run_mira.py
python -m unittest discover -s tests -v
```

`mira/gui.py` chứa giao diện; `mira/agent.py` gọi Ollama và giới hạn công cụ; `mira/workspace.py` kiểm tra đường dẫn, diff và sao lưu; `mira/storage.py` lưu dữ liệu cục bộ; `mira/preferences.py` chọn sở thích theo ngữ cảnh. Không yêu cầu thư viện Python ngoài standard library cho tính năng hiện có.
