# Mira — trợ lý AI cá nhân trên máy tính

Mira có giao diện chat rõ ràng ngay khi mở: ô **NHẬP TIN NHẮN CHO MIRA** nằm ở dưới khung hội thoại, nút **Gửi ➤** ở bên phải. Mira có tính cách nữ và trò chuyện bằng tiếng Việt. Bạn có thể đổi tên trợ lý trong Cài đặt.

## Cài đặt trên Windows

1. Cài Python 3.11 trở lên từ https://www.python.org/downloads/ (chọn “Add python.exe to PATH” nếu trình cài đặt có tùy chọn này).
2. Cài Ollama từ https://ollama.com/download/windows và mở Ollama. Ollama yêu cầu Windows 10 22H2 trở lên.
3. Mở PowerShell, chạy lệnh sau để tải mô hình (khoảng 2,5 GB):

       ollama pull qwen3:4b

4. Tải mã nguồn từ repo GitHub (Code → Download ZIP), giải nén và nhấn đúp **start_windows.bat**.
5. Trong cửa sổ Mira, gõ vào ô chat ở dưới cùng và nhấn **Enter** hoặc nút **Gửi ➤**. Dùng **Shift+Enter** để xuống dòng.

Nếu cửa sổ không mở, mở PowerShell trong thư mục đã giải nén và chạy: `py -3 run_mira.py`. Cửa sổ lệnh sẽ hiển thị lỗi. Mira chỉ dùng thư viện chuẩn Python, không cần pip install.

## Các phần chính

- **Trò chuyện:** khung chat và ô nhập luôn hiện; lịch sử từng cuộc trò chuyện ở cột trái. Tạo mới, đổi tên, xóa hoặc xuất chat thành Markdown.
- **Mô hình:** Mira tự kiểm tra Ollama khi mở, báo rõ trường hợp chưa mở Ollama hoặc chưa tải mô hình. Nút **Mô hình & cài đặt** cho phép đổi tên và chọn mô hình đã cài.
- **Bộ nhớ:** nút **Bộ nhớ của Mira** để thêm, sửa, quên các điều bạn muốn Mira nhớ. Đây là bộ nhớ đưa vào ngữ cảnh, **chưa phải fine-tune/training lại trọng số**.
- **File & code:** bấm **Chọn thư mục** để cấp phạm vi file. Bấm **Chọn file** để đưa đường dẫn vào câu hỏi. Mira có thể tìm/đọc file UTF-8 và đề xuất sửa; mọi thay đổi phải qua cửa sổ xem diff và bấm **Duyệt và ghi file**. Bản cũ được sao lưu.
- **Kiểm thử:** nút **Chạy kiểm thử** phát hiện dự án Python có thư mục tests hoặc dự án npm có package.json. Ứng dụng cho bạn xem và xác nhận lệnh trước khi chạy code trong thư mục dự án.

Lịch sử chat của bản cũ được tự đưa sang danh sách hội thoại mới ở lần mở đầu; bộ nhớ và cài đặt cũ được giữ. Dữ liệu cá nhân nằm ở %LOCALAPPDATA%\Mira; mã nguồn trên GitHub không chứa dữ liệu chat của bạn.

## Phím và tình huống thường gặp

| Việc cần làm | Cách thực hiện |
| --- | --- |
| Gửi tin nhắn | Enter hoặc Gửi ➤ |
| Xuống dòng | Shift+Enter |
| Chọn file để hỏi | Chọn thư mục trước, rồi Chọn file |
| Trợ lý báo chưa kết nối | Mở Ollama, bấm Kiểm tra lại |
| Trợ lý báo thiếu mô hình | Chạy ollama pull qwen3:4b, bấm Kiểm tra lại |
| Xem lại file đã sửa | Xem thư mục backups trong %LOCALAPPDATA%\Mira |

## Giới hạn và quyền

Mira chỉ gọi Ollama trên máy tại 127.0.0.1:11434 khi bạn dùng mô hình cục bộ. Thư mục được chọn là phạm vi duy nhất để AI đọc và đề xuất sửa file; file bí mật thường gặp, symlink và thư mục sinh tự động bị loại trừ. Bản này chưa có nhận diện màn hình, giọng nói, thao tác chuột/bàn phím tự động hoặc truy cập web. Các khả năng đó cần thiết kế quyền riêng khi bổ sung.

Để tự kiểm tra mã nguồn:

    python -m unittest discover -s tests -v
