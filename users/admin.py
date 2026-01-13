from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import mark_safe # Để hiển thị ảnh HTML
from leaflet.admin import LeafletGeoAdmin
from .models import User, SearchHistory

# --- 1. CẤU HÌNH ADMIN CHO USER ---
# Phải kế thừa UserAdmin để giữ các tính năng đổi mật khẩu, phân quyền gốc của Django
class CustomUserAdmin(UserAdmin):
    # Các cột hiển thị ở danh sách user bên ngoài
    list_display = ('username', 'email', 'full_name', 'phone', 'role', 'is_staff')
    
    # Bộ lọc và tìm kiếm
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'full_name', 'phone', 'email')
    
    # Cấu hình FORM CHỈNH SỬA (Edit)
    # Thêm các field mới (phone, role, avatar...) vào form
    fieldsets = UserAdmin.fieldsets + (
        ('Thông tin bổ sung', {
            'fields': ('phone', 'role', 'full_name', 'avatar', 'avatar_preview')
        }),
    )
    
    # Cấu hình FORM TẠO MỚI (Add)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Thông tin bổ sung', {
            'fields': ('phone', 'role', 'full_name', 'avatar')
        }),
    )
    
    # Khai báo trường chỉ đọc (xem trước ảnh)
    readonly_fields = ('avatar_preview',)

    # Hàm tạo HTML hiển thị ảnh avatar nhỏ
    def avatar_preview(self, obj):
        if obj.avatar:
            return mark_safe(f'<img src="{obj.avatar.url}" style="width: 100px; height: auto; border-radius: 5px;" />')
        return "Chưa có ảnh"
    avatar_preview.short_description = "Xem trước Avatar"


# --- 2. CẤU HÌNH ADMIN CHO SEARCH HISTORY (BẢN ĐỒ) ---
class SearchHistoryAdmin(LeafletGeoAdmin):
    list_display = ('user', 'keyword', 'create_at')
    list_filter = ('create_at',) # Lọc theo ngày tìm kiếm
    search_fields = ('keyword', 'user__username', 'user__email') # Tìm theo từ khóa hoặc tên user
    
    # Cấu hình bản đồ Leaflet trong trang Admin
    settings_overrides = {
       'DEFAULT_CENTER': (10.0452, 105.7469), # Tọa độ Cần Thơ
       'DEFAULT_ZOOM': 12,
       'MIN_ZOOM': 5,
       'MAX_ZOOM': 18,
    }

# --- 3. ĐĂNG KÝ MODEL ---
admin.site.register(User, CustomUserAdmin)
admin.site.register(SearchHistory, SearchHistoryAdmin)