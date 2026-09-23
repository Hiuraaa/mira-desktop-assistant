# Mira — trợ lý AI cá nhân trên máy tính

Mira là ứng dụng desktop dành cho Windows, trò chuyện bằng tiếng Việt qua mô hình Ollama chạy trên máy bạn. Bạn có thể nhờ Mira giải thích, viết code, tìm/đọc file, kiểm tra cú pháp Python và đề xuất sửa file trong thư mục bạn chọn. Tên gọi và cách xưng hô của Mira có thể chỉnh trong **Mô hình & cài đặt**.

## Chạy Mira trên Windows

1. Cài [Python 3.11+](https://www.python.org/downloads/) và chọn **Add python.exe to PATH** trong trình cài đặt.
2. Cài [Ollama cho Windows](https://ollama.com/download/windows) và mở Ollama.
3. Mở PowerShell, chạy `ollama pull qwen3:4b` và đợi tải xong. Chọn mô hình khác có hỗ trợ gọi công cụ nếu muốn.
4. Giải nén ZIP, nhấn đúp **`start_windows.bat`**. Không cần `pip install` cho bản cơ bản.
5. Màn hình mở thẳng vào chat: ô **NHẮN MIRA** màu sáng nằm ngay dưới vùng hội thoại. Nhập câu hỏi rồi bấm **Gửi** hoặc Enter. **Shift+Enter** xuống dòng. Thanh trạng thái phía trên cho biết Ollama đã sẵn sàng chưa; bấm **Cách cài** nếu cần.

Máy yếu có thể mất thời gian để tạo câu trả lời đầu tiên. Khi mô hình chưa được tải, Mira sẽ hiển thị hướng dẫn ngay trên màn hình. Nếu Python Launcher (`py`) không có, file `.bat` sẽ thử `python`.

## Các việc thường làm

| Việc | Cách dùng |
| --- | --- |
| Trò chuyện | Nhập ở **NHẮN MIRA**, bấm Gửi. Lỗi kết nối có nút **Thử gửi lại**. |
| Giữ nhiều cuộc trò chuyện | Bấm **+ Cuộc trò chuyện mới**; chọn lịch sử ở cột trái. Có thể đổi tên, xóa hoặc xuất cuộc trò chuyện hiện tại ra `.txt`. |
| Làm việc với code/file | Bấm **Chọn thư mục làm việc**. Mira chỉ đọc/tìm và đề xuất sửa file trong thư mục đó. Có thể bỏ quyền trong **Mô hình & cài đặt**. |
| Sửa file | Mira hiển thị diff đầy đủ. Chọn **Duyệt và ghi file** hoặc **Từ chối**. File cũ được sao lưu trước khi ghi. |
| Kiểm tra Python | Hỏi “Kiểm tra cú pháp `src/app.py`”. Mira phân tích cú pháp mà không chạy chương trình. |
| Dạy dần | Bấm **Dạy Mira / bộ nhớ** để thêm, sửa hoặc xóa điều cần nhớ. Đây là ghi nhớ đưa vào các lượt chat, không huấn luyện lại mô hình. |
| Hỏi về ảnh màn hình | Tự chụp/lưu ảnh PNG hoặc JPEG, bấm **Đính kèm ảnh**, chọn file, rồi gửi. Chạy `ollama pull qwen3-vl:4b` rồi chọn mô hình này trong **Mô hình & cài đặt**; `qwen3:4b` mặc định chỉ dùng cho văn bản. Ảnh chỉ gửi trong lượt đó, lịch sử lưu tên file chứ không lưu ảnh. |

Nếu bạn đã dùng bản đầu, lịch sử trong `conversation.json` sẽ được nhập tự động vào mục **Cuộc trò chuyện trước đây**. Bộ nhớ cũ vẫn được giữ.

## Quyền truy cập và giới hạn

- Mira kết nối với Ollama qua `127.0.0.1:11434`. Nội dung chat, bộ nhớ, những file được Mira đọc và ảnh bạn chủ động đính kèm sẽ được gửi tới mô hình đã chọn. Nếu chọn mô hình cloud trong Ollama, cách xử lý dữ liệu phụ thuộc dịch vụ mô hình đó.
- Chỉ các file trong thư mục do bạn chọn mới được đọc/tìm/sửa. Mira từ chối đường dẫn ra ngoài, symlink, một số file thường chứa thông tin đăng nhập và thư mục sinh tự động (`.git`, `node_modules`, `.venv`...). File đọc tối đa 64 KiB, file sửa tối đa 128 KiB, văn bản UTF-8. Mỗi lần ghi đều phải được bạn duyệt.
- Ứng dụng không tự chạy lệnh, điều khiển chuột, đọc màn hình liên tục hay nghe microphone. Để Mira xem ảnh, bạn cần chọn ảnh thủ công và dùng mô hình có hỗ trợ ảnh. Code và lời khuyên do AI tạo ra có thể sai; hãy xem diff trước khi ghi.
- Cài đặt, hội thoại, bộ nhớ và bản sao file cũ nằm ở `%LOCALAPPDATA%\Mira` trên Windows (hoặc `~/.local/share/Mira` trên Linux); không có trong ZIP hay repo. Bản sao nằm trong `backups` và có thể được chép về vị trí cũ để phục hồi.

## Dành cho người phát triển

```bash
python run_mira.py
python -m unittest discover -s tests -v
```

`mira/gui.py` chứa giao diện; `mira/agent.py` gọi Ollama và giới hạn công cụ; `mira/workspace.py` kiểm tra đường dẫn, diff và sao lưu; `mira/storage.py` lưu dữ liệu cục bộ. Không yêu cầu thư viện Python ngoài standard library cho tính năng hiện có.
