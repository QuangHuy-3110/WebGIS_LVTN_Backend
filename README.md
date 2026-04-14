# Web GIS - Backend Repository

Đây là thư mục chứa mã nguồn Backend cho hệ thống Web GIS. Phần này quản lý Cơ sở dữ liệu Không gian (PostGIS), hệ thống API bằng Django REST Framework và Khối xử lý Trí tuệ Nhân tạo (Trích xuất thông tin ảnh AI, Tìm đường).

## 🚀 Tính năng nổi bật
* **Hệ thống API:** RESTful API linh hoạt được xây dựng từ Django Rest Framework & Django REST Framework GIS hỗ trợ tối đa GeoJSON.
* **Trích xuất thông tin ảnh AI (Signboard Extraction):** Triển khai luồng nhận diện và tách thông tin ảnh bảng hiệu với Ultralytics (YOLO), PaddleOCR và Huggingface Transformers.
* **Thuật toán Định tuyến & Dữ liệu lộ trình:** Tích hợp Dijkstra & A* để tối ưu truy vấn đường đi, sử dụng cấu trúc đồ thị mạng lưới đường xá được xây dựng từ dữ liệu OpenStreetMap (OSM).
* **Cơ sở dữ liệu Không gian:** Tích hợp PostGIS thông qua module `django-leaflet` và thư viện `rtree` quản lý index không gian tối tân.
* **Xử lý Realtime:** Django Channels và Daphne hỗ trợ ứng dụng theo dõi hay cập nhật trạng thái ngay lặp tức.

## 🛠 Công nghệ sử dụng
* Language: Python 3
* Framework: [Django](https://www.djangoproject.com/) & [Django Rest Framework](https://www.django-rest-framework.org/)
* AI & Machine Learning: [PyTorch](https://pytorch.org/), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [Ultralytics](https://github.com/ultralytics/ultralytics)
* CSDL: PostgreSQL + PostGIS (Production / Docker)
* WebSockets: Django Channels, Daphne

## ⚙️ Hướng dẫn cài đặt và chạy Local từ A-Z

Phần này hướng dẫn triển khai môi trường máy chủ và cơ sở dữ liệu.

### Yêu cầu nền tảng
* Python 3.9+ 
* Docker & Docker Compose (Cho việc khởi chạy Database tiện dụng)

### BƯỚC 1: Khởi chạy Thế giới dữ liệu (Database) 
Chúng ta cần một CSDL PostgreSQL có sự hỗ trợ của thành phần không gian GIS (PostGIS). Bạn có thể sử dụng Docker Compose đi kèm:
1. Tại thư mục có chứa cấu hình `docker-compose.yml`, mở Terminal và chạy lệnh:
   ```bash
   docker-compose up -d db
   ```
2. Mở CSDL qua phần mềm (DBeaver, PGAdmin, ...), kết nối cổng `5433` (hoặc cổng mapping đã cấu hình), sử dụng account đã cấu hình (Ví dụ mặc định `myuser` / password `mypassword`).
3. Truy vấn SQL để kích hoạt PostGIS cho Database sử dụng tính toán không gian:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

### BƯỚC 2: Cài đặt Môi trường Python (Virtual Env)
Mở Terminal, di chuyển vào thư mục gốc của repository (`backend/`):
```bash
python -m venv venv
```
Kích hoạt môi trường ảo vừa tạo:
* Trên Windows: `.\venv\Scripts\activate`
* Trên MacOS/Linux: `source venv/bin/activate`

### BƯỚC 3: Cài đặt thư viện AI và Web Server
Tiến hành nạp môi trường lập trình từ list requirements:
```bash
pip install -r requirements.txt
```
*(Lưu ý: Quá trình này sẽ bao gồm gói Machine Learning (Torch, PaddleOCR, Transformers) nên dung lượng khá lớn. Hãy đảm bảo mạng tốt. Tuỳ vào setup của máy tính, nếu có GPU nên lưu ý cài gói Torch phiên bản CUDA theo tài liệu pytorch.org).*

### BƯỚC 4: Cấu hình Môi trường (.env)
Tại thư mục gốc thư mục Backend này, cấp một File `.env` tham chiếu: 
```env
MAPTILER_KEY=your-maptiler-key
SECRET_KEY=your-secret
DEBUG=True
```
Đồng thời, đảm bảo file `settings.py` đã kết nối tham chiếu chuẩn xác tới IP/Port của Postgres DB (Port 5433 đối với Docker Local).

### BƯỚC 5: Thiết lập Cấu trúc CSDL và Migrations
Chạy chuỗi lệnh sau để kiến trúc các Bảng SQL tự động và tạo User Siêu Quản Trị (Admin):
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### BƯỚC 6: Khởi chạy API Máy Chủ
Dùng lệnh này bắt đầu lắng nghe mọi API Request từ Client frontend gởi lại:
```bash
python manage.py runserver
```
*(Hoặc dùng Daphne nếu muốn Test khả năng WebSocket `daphne -b 0.0.0.0 -p 8000 backend.asgi:application`)*

Hệ Backend khởi chạy xong nằm tại địa chỉ `http://127.0.0.1:8000`. Cổng Web Admin dành cho người làm việc là `http://127.0.0.1:8000/admin/`.
