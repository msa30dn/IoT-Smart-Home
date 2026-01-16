# IoT-Smart-Home


## Miêu tả hệ thống

**1) Hai bo mạch ESP32**

Node 1: "ESP32 Cảm biến" đọc dữ liệu từ hai cảm biến nhiệt độ (bên trong phòng và không khí tự nhiên bên ngoài), sau đó gửi các giá trị đo được lên MQTT topic đặt trên máy WSL. Node 1 không cần gửi quá dầy đặc liên tục, thay vào đó cứ n (ví dụ 10) giây 1 một lần.

Node 2: ESP32 Điều khiển", nó đăng ký (subscribe) topic nhận lệnh từ MQTT, và điều khiển động cơ và rơ-le dựa trên các tín hiệu/lệnh điều khiển nhận được. Ngoài ra nó cho phép Điều khiển thủ công qua Blynk với Blynk.Edgent được tích hợp. Nếu "auto mode" bị chọn tắt (từ Blynk) thì node bỏ qua các lệnh gửi từ Local controller, mà thực thi theo lệnh điều khiển thủ công từ Blynk - mặc định "auto mode" is ON)

*Ghi chú: Sẽ rất tốt nếu hai bo mạch có màn hình hiển thị gì đó cho hấp dẫn*

**2) Local controller** 

Local controller đóng vai trò máy chủ cục bộ (dùng WSL Ubuntu trên laptop mô phỏng), nó cung cấp một MQTT broker (Mosquitto), đồng thời  là "bộ não" nơi control logic được áp dụng, và là nơi điều phối hoạt động tại chỗ. Tại đây, logic điều khiển (có thể đơn giản hóa viết bằng Python) đọc và xử lý dữ liệu cảm biến (gửi từ ESP32 node 1 qua MQTT), đưa ra quyết định, cuối cùng gửi lệnh điều khiển đến ESP32 điều khiển (node 2) qua MQTT. Tốt hơn nữa, nó có thể được lập trình để điều khiển một cách hợp lý để bảo vệ các thiết bị đồng thời tiết kiệm xử lý tính toán.

**3) IoT Cloud (Blynk)**

Được áp dụng cho ESP32 Điều khiển (node 2), cho phép người dùng bật/tắt thủ công động cơ và rơ-le. Ngoài ra, nó cũng giúp thiết lập tham số cấu hình MQTT (ví dụ ip, host của MQTT broker là gì) cho ESP32 Điều khiển sử dụng.

## Cấu trúc các MQTT messages (JSON)

**1) Message gửi từ ESP32 node 1 tới Local Controller**

```json
{
  "device_id": "esp32_sensor_01",
  "interval_s": 10,
  "unit": "C",
  "ts": 1736881010,
  "temperatures": {
    "inside": {
      "sensor_id": "temp_inside_1",
      "value": 26.1
    },
    "outside": {
      "sensor_id": "temp_outside_1",
      "value": 22.0
    }
  }
}
```


**2) Message gửi từ Local Controller tới node 2 cho các trường hợp**

```json
{
  "cmd_id": 1042,
  "source": "local",
  "mode_request": "auto",
  "relay": 0,
  "fan": 1,
  "ts": 1736882000,
  "reason": "inside>26 and outside<=22 -> prefer_fan"
}
```

```json
{
  "cmd_id": 1044,
  "source": "local",
  "mode_request": "auto",
  "relay": 0,
  "fan": 0,
  "ts": 1736882060,
  "reason": "inside<=threshold -> idle"
}
```

```json
{
  "cmd_id": 88,
  "source": "blynk",
  "mode_request": "manual",
  "relay": 1,
  "fan": 0,
  "manual_for_s": 600,
  "ts": 1736882100
}
```

Và còn nữa....


---

### Tiến độ và tình trạng công việc

1) Xác định yêu cầu cơ bản (baseline), miêu tả và thiết kế hệ thống --> done (S. Hùng)

2) Giải pháo sử dụng WSL (Ubuntu) của Windows để cài một MQTT broker. Đồng thời định nghĩa các message giao tiếp giữa các thành phần MQTT  --> done (S. Hùng)

3) Viết Python code cho  "Local Controller" - chịu trách nhiệm chính về logic điều khiển và tương tác với 2 ESP32 nodes qua MQTT --> in progress (almost done) (S. Hùng)

4) Thiết kế Blynk Dashboard cho Điều khiển thủ công --> done (S. Hùng)

5) Code nhúng mẫu để sử dụng IoT CLoud Blynk điều khiển thủ công qua Internet. Đồng thời tích hợp chức năng đọc các lệnh điều khiển gửi từ  "Local Controller" qua MQTT vào cùng một code với Blynk. -  Lưu ý chỉ có phần liên quan Blynk và kết nối MQTT để đọc lấy ra lệnh điều khiển, chưa có code cho việc điều khiển các thiết bị chấp hành (quạn thông gió, điều hòa) thực sự --> in progress (đã xong phần cơ bản, đã gửi cho team xem trước) (S. Hùng)

6) Các việc khác ...