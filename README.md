# Mira — trợ lý AI cá nhân trên máy tính

Mira là bản đầu tiên của trợ lý cá nhân có tính cách nữ, giao diện trò chuyện bằng tiếng Việt, giúp xem và sửa file văn bản hoặc code trong **thư mục bạn chọn**. Bạn có thể dạy Mira những điều cần ghi nhớ và xóa chúng bất cứ lúc nào.

## Cài trên Windows

1. Cài **Python 3.11 trở lên** từ [python.org](https://www.python.org/downloads/) và bật tùy chọn `Add python.exe to PATH` khi cài. Python trên Windows thường có sẵn Tkinter.
2. Cài [Ollama cho Windows](https://ollama.com/download/windows), sau đó mở Ollama.
3. Mở PowerShell và tải một mô hình có hỗ trợ gọi công cụ:

   ```powershell
   ollama pull qwen3:4b
   ```

4. Giải nén dự án, nhấn đúp **`start_windows.bat`**. Nếu máy không nhận lệnh `py`, mở PowerShell tại thư mục dự án và chạy `python run_mira.py`.
5. Nhập lời nhắn để trò chuyện. Bấm **Chọn thư mục** để Mira có thể đọc/tìm và đề xuất sửa file trong thư mục đó. Gửi bằng nút **Gửi** hoặc `Ctrl+Enter`.

Không cần `pip install`: ứng dụng chỉ dùng thư viện chuẩn Python. Mô hình được tải riêng bởi Ollama; dung lượng và tốc độ phụ thuộc vào mô hình cũng như cấu hình máy. Bạn có thể đổi tên mô hình trong giao diện sau khi tải mô hình khác có hỗ trợ công cụ.

## Mira có thể làm gì?

- Trò chuyện, giải thích, gợi ý sửa lỗi và viết code.
- Liệt kê, tìm nội dung và đọc file UTF-8 trong thư mục đã chọn.
- Đề xuất tạo hoặc sửa file: hiện **toàn bộ diff** để bạn chọn **Duyệt và ghi file** hoặc **Từ chối**. File cũ được sao lưu trước khi ghi.
- **Dạy Mira**: thêm tối đa 50 điều (mỗi điều tối đa 500 ký tự), xem và quên từng điều. Những điều này được đưa vào ngữ cảnh mỗi lần trò chuyện; đây là **bộ nhớ cá nhân**, chưa phải huấn luyện lại trọng số mô hình.
- Lưu 40 tin nhắn gần đây trên máy. **Chat mới** xóa lịch sử trò chuyện hiện tại, không xóa bộ nhớ đã dạy.

Ví dụ: “Xem `src/app.py` và giải thích lỗi”, “Tìm nơi dùng `login` trong dự án này”, “Sửa `index.html` cho dễ đọc trên điện thoại”.

## Giới hạn và quyền riêng tư

- Bản này chưa nhìn màn hình, điều khiển chuột/bàn phím, chạy lệnh, duyệt web hoặc trò chuyện bằng giọng nói. Các khả năng đó có thể bổ sung sau theo quyền bạn chọn.
- Mira chỉ gửi câu hỏi, bộ nhớ và phần file được đọc tới **Ollama tại `127.0.0.1:11434` trên chính máy này**. Ứng dụng không có tài khoản hay API key. Hãy dùng mô hình đã tải về để chạy cục bộ; việc chọn mô hình cloud trong Ollama sẽ theo cơ chế riêng của Ollama.
- Mira từ chối đường dẫn ngoài thư mục đã chọn, symlink, file thông tin đăng nhập phổ biến (`.env`, `.pem`, `.key`, v.v.) và thư mục sinh tự động như `node_modules` và `.git`. Chỉ sửa file UTF-8 tối đa 128 KiB; đọc file tối đa 64 KiB. Không có công cụ xóa file hoặc chạy lệnh.
- Lịch sử, bộ nhớ, cài đặt và bản sao file cũ nằm ở `%LOCALAPPDATA%\Mira` trên Windows (hoặc `~/.local/share/Mira` trên Linux). Chúng không được đưa vào repo GitHub. Bản sao ở thư mục `backups`; có thể phục hồi bằng cách chép nội dung bản sao về đường dẫn gốc.
- Phản hồi và mã AI tạo ra có thể sai. Hãy xem diff trước khi duyệt và kiểm tra lại dự án sau khi sửa.

## Chạy và kiểm thử cho người phát triển

```bash
python run_mira.py
python -m unittest discover -s tests -v
```

Kiến trúc: `mira/agent.py` trao đổi với Ollama và giới hạn vòng gọi công cụ; `mira/workspace.py` kiểm soát đường dẫn, phê duyệt và sao lưu; `mira/storage.py` lưu bộ nhớ/lịch sử; `mira/gui.py` chứa giao diện.

### Hướng phát triển tiếp

Chế độ giọng nói với giọng nữ do bạn chọn, xem ảnh màn hình theo yêu cầu, chạy kiểm thử code sau khi bạn duyệt lệnh, hỗ trợ nhiều loại file, và tùy chọn mô hình cloud nếu máy yếu. Mỗi quyền mới cần có nút bật và phạm vi rõ ràng.
