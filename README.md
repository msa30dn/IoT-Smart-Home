# IoT-Smart-Home


## Miêu tả hệ thống

**1) Hai bo mạch ESP32**

Node 1: "ESP32 Cảm biến" đọc dữ liệu từ hai cảm biến nhiệt độ (bên trong phòng và không khí tự nhiên bên ngoài), sau đó gửi các giá trị đo được lên MQTT topic đặt trên máy WSL.

Node 2: ESP32 Điều khiển", nó đăng ký (subscribe) topic nhận lệnh từ MQTT, và điều khiển động cơ và rơ-le dựa trên các tín hiệu/ lệnh điều khiển nhận được. Ngoài ra nó cho phép Điều khiển thủ công qua Blynk với Blynk.Edgent được tích hợp. Nếu "auto mode" bị chọn tắt (từ Blynk) thì node bỏ qua các lệnh gửi từ Local controller, mà thực thi theo lệnh điều khiển thủ công từ Blynk - mặc định "auto mode" is ON)

**2) Local controller** 

Local controller đóng vai trò máy chủ cục bộ (dùng WSL Ubuntu trên laptop mô phỏng), nó cung cấp một MQTT broker (Mosquitto), đồng thời  là "bộ não" nơi control logic được áp dụng, và là nơi điều phối hoạt động tại chỗ. Tại đây, logic điều khiển (có thể đơn giản hóa viết bằng Python) đọc và xử lý dữ liệu cảm biến (gửi từ ESP32 node 1 qua MQTT), đưa ra quyết định, cuối cùng gửi lệnh điều khiển đến ESP32 điều khiển (node 2) qua MQTT.


**3) IoT Cloud (Blynk)**

Được áp dụng cho  ESP32 ESP32 Điều khiển (node 2), cho phép người dùng bật/tắt thủ công động cơ và rơ-le.

