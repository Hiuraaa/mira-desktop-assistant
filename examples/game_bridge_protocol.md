# Kết nối game với Mira trên PC

Mở Mira → **♟ Chơi game với Mira** → **Bật kết nối**. Mã kết nối chỉ dùng trong phiên này và chỉ cấp cho game/adapter bạn tin tưởng. **Chơi Cờ caro mẫu** mở một game thật trong cửa sổ riêng: bạn đánh X, Mira đánh O. Sau nước X, bấm **Cho Mira phản ứng sự kiện mới nhất**, hoặc bật **Tự nhận xét sự kiện game** trước khi chơi. Mỗi nước O vẫn phải được bạn duyệt trên Mira; muốn dừng ngay, bấm **Tắt**.

Mira chỉ nghe cổng `127.0.0.1:<port>` trên PC; app điện thoại và game trên máy khác không thể kết nối trực tiếp. Không để mã hiện trong ảnh chụp màn hình gửi lên AI. Kết nối đóng khi tắt app. Game chỉ được cung cấp dữ liệu bạn chủ động cho adapter gửi; Mira không tự đọc bộ nhớ tiến trình, không tự chụp màn hình hay gửi phím cho game qua cổng này.

## Tích hợp game khác

Viết adapter cho game có thể lấy trạng thái bàn/chơi và áp dụng nước đi qua API của chính game đó. Mẫu `game_demo.py` là một adapter hoàn chỉnh bằng thư viện Python có sẵn. Cổng của Mira lấy cảm hứng từ việc tách **context** và **registered actions** trong Neuro SDK, nhưng **không phải giao thức WebSocket Neuro SDK**.

Adapter gọi ba endpoint HTTP, mỗi lần đều gửi `X-Mira-Game-Key: <mã>`; các POST gửi `Content-Type: application/json`. Không ghi mã vào code hoặc đưa lên GitHub.

1. `POST /register` một lần khi bắt đầu game:

   ```json
   {"game":"Cờ caro 3x3","actions":[{"name":"play_cell","description":"Đặt quân vào ô trống","options":["1","2","3","4","5","6","7","8","9"]}]}
   ```

2. Khi đến lượt, `POST /event` trạng thái hiện tại, sự kiện và **chỉ các lựa chọn đang hợp lệ**:

   ```json
   {"game":"Cờ caro 3x3","context":"Người chơi vừa đánh X; tới lượt Mira.","state":"X 2 3\n4 O 6\n7 8 9","available":{"play_cell":["2","3","4","6","7","8","9"]}}
   ```

   Phản hồi có `id` của lượt. Để Mira bình luận mà không chọn nước, gửi `"available":{}`.

3. `GET /action?id=<id>` khoảng một lần/giây. Khi trả `{"status":"chosen","action":{"name":"play_cell","choice":"2"}}`, adapter **kiểm tra lại** ô 2 vẫn hợp lệ, áp dụng nước đi qua game rồi gửi trạng thái mới qua `/event`. Một quyết định chỉ được trả **một lần**. `waiting`, `denied`, `delivered`, `expired` là các trạng thái khác; một lượt hết hạn sau 3 phút. Nếu bị từ chối, người chơi có thể yêu cầu game gửi một lượt mới.

Đăng ký tối đa 8 hành động, 12 lựa chọn cho mỗi hành động. Sự kiện tối đa 700 ký tự, trạng thái 1.200 ký tự, gói JSON tối đa 8 KiB. Mira hỏi duyệt từng nước, kiểm tra danh sách nước đi sau lúc duyệt và không nhận nước của lượt đã cũ. Trình nối không được dùng để thực thi shell, mở file, hoặc điều khiển chuột/bàn phím của máy. Để Mira chọn được nước, hãy dùng model Ollama hỗ trợ gọi công cụ; model chat thuần vẫn có thể bình luận nhưng không tự đánh.
