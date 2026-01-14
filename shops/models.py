from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import Avg, Count
from django.contrib.gis.geos import Point

class Category (models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Store (models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='owned_stores')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    phone = models.CharField(max_length=15, verbose_name="So dien thoai cua hang", null=True, blank=True)
    email = models.CharField(max_length=255, verbose_name="Email cua hang")
    location = models.PointField(verbose_name='Toa do')
    state = models.CharField(max_length=50, verbose_name="Trang thai cua hang")
    describe = models.TextField(blank=True)
    open_time = models.TimeField(verbose_name="Gio mo cua")
    close_time = models.TimeField(verbose_name="Gio dong cua")
    rating_avg = models.FloatField(default=0.0, verbose_name="Diem danh gia trung binh") # Tương ứng sosaoCH
    rating_count = models.IntegerField(default=0, verbose_name="So luot danh gia")
    is_active = models.BooleanField(default=True, verbose_name="Kích hoạt")
    def __str__(self):
        return self.name

    def update_rating(self):
        stats = self.reviews.aggregate(average=Avg('rating'), count=Count('id'))
        
        self.rating_avg = stats['average'] or 0.0 # Nếu chưa có review nào thì là 0
        self.rating_count = stats['count'] or 0
        self.save() 

class StoreImage (models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="image")
    image = models.ImageField(upload_to='stores/', verbose_name="Hinh anh", null=True, blank=True)
    describe = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    state = models.CharField(max_length=50)
    time_up = models.TimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.store.name}"

class ApprovalProfile (models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ]
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='store')
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitter')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='approvals')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_up = models.DateTimeField(auto_now_add=True)
    date_sign = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

# --- THÊM ĐOẠN NÀY VÀO CUỐI FILE models.py ---
from django.db.models.signals import post_save
from django.dispatch import receiver
import json

@receiver(post_save, sender=ApprovalProfile)
def auto_process_approval(sender, instance, created, **kwargs):
    """
    Hàm này tự động chạy mỗi khi một ApprovalProfile được Duyệt.
    """
    if instance.status == 'approved':
        print(f"⚡ SIGNAL KÍCH HOẠT: Đang xử lý hồ sơ #{instance.id}")
        try:
            # 1. IMPORT CẦN THIẾT (Để tránh vòng lặp import)
            from .models import StoreImage
            
            # 2. KHỞI TẠO BIẾN QUAN TRỌNG (Sửa lỗi chưa khai báo biến store)
            store = instance.store
            if isinstance(instance.note, str):
                changes = json.loads(instance.note)
            else:
                changes = instance.note

            # --- TRƯỜNG HỢP A: DUYỆT YÊU CẦU TẠO CỬA HÀNG MỚI ---
            if changes.get('action') == 'CREATE_NEW':
                # 1. Kích hoạt cửa hàng
                store.is_active = True
                store.state = 'active'
                
                # 2. Public TOÀN BỘ ảnh của quán này
                StoreImage.objects.filter(store=store).update(state='public')
                
                print(f"🎉 [Signal] Đã kích hoạt cửa hàng mới & Public ảnh: {store.name}")

            # --- TRƯỜNG HỢP B: DUYỆT YÊU CẦU SỬA ĐỔI THÔNG TIN ---
            else:
                # 1. Xử lý ảnh (Chỉ ảnh cụ thể)
                if 'new_images' in changes and isinstance(changes['new_images'], list):
                    StoreImage.objects.filter(id__in=changes['new_images']).update(state='public')
                    print(f"✅ [Signal] Đã public {len(changes['new_images'])} ảnh mới.")

                if 'deleted_images' in changes and isinstance(changes['deleted_images'], list):
                    StoreImage.objects.filter(id__in=changes['deleted_images']).delete()
                    print(f"🗑️ [Signal] Đã xóa {len(changes['deleted_images'])} ảnh cũ.")

                print(f"✏️ [Signal] Đang cập nhật thông tin cửa hàng: {store.name}")

            # --- PHẦN CHUNG: CẬP NHẬT THÔNG TIN TEXT & VỊ TRÍ ---
            # (Áp dụng cho cả tạo mới và sửa đổi để đảm bảo dữ liệu mới nhất)
            
            # 1. Cập nhật các trường thông tin cơ bản
            fields_to_update = ['name', 'address', 'describe', 'phone', 'email', 'open_time', 'close_time', 'category']
            has_change = False
            
            for field in fields_to_update:
                if field in changes: # Nếu có dữ liệu gửi lên thì mới sửa
                    setattr(store, field, changes[field])
                    has_change = True

            # 2. Cập nhật tọa độ (nếu có)
            if 'latitude' in changes and 'longitude' in changes:
                try:
                    lat = float(changes['latitude'])
                    lng = float(changes['longitude'])
                    store.location = Point(lng, lat) # GeoDjango: (Longitude, Latitude)
                    has_change = True
                    print(f"📍 [Signal] Cập nhật tọa độ: {lat}, {lng}")
                except ValueError:
                    print("❌ Lỗi định dạng tọa độ")

            # 3. Lưu lại Store nếu có thay đổi
            if has_change or changes.get('action') == 'CREATE_NEW':
                store.save()
                print("✅ [Signal] Lưu Store thành công.")

        except Exception as e:
            print(f"❌ [Signal] Lỗi khi xử lý duyệt: {e}")