from django.contrib import admin
from django.utils.html import mark_safe # Dùng để hiển thị ảnh
from leaflet.admin import LeafletGeoAdmin
from .models import Category, Store, StoreImage, ApprovalProfile

# --- 1. QUẢN LÝ DANH MỤC (Tự động Slug) ---
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'id')
    # Tự động sinh slug từ name khi gõ
    prepopulated_fields = {'slug': ('name',)}

# --- 2. QUẢN LÝ ẢNH (Hiển thị preview ảnh) ---
class StoreImageInline(admin.TabularInline):
    model = StoreImage
    extra = 1
    # Chỉ đọc trường preview (vì trường này là hàm tự viết)
    readonly_fields = ('image_preview',) 

    # Hàm để hiển thị ảnh nhỏ
    def image_preview(self, obj):
        if obj.image:
            # Hiển thị ảnh kích thước 100px
            return mark_safe(f'<img src="{obj.image.url}" style="width: 100px; height:auto;" />')
        return "Chưa có ảnh"
    image_preview.short_description = "Xem trước"

# --- 3. QUẢN LÝ CỬA HÀNG (Bộ lọc & Map) ---
class StoreAdmin(LeafletGeoAdmin):
    # Các cột hiển thị
    list_display = ('name', 'category', 'address', 'rating_avg', 'state')
    
    # Bộ lọc bên tay phải (Rất quan trọng khi dữ liệu nhiều)
    list_filter = ('category', 'state', 'rating_avg')
    
    # Tìm kiếm
    search_fields = ('name', 'address', 'email')
    
    # Các trường chỉ đọc (Admin không được sửa điểm đánh giá thủ công)
    readonly_fields = ('rating_avg', 'rating_count')

    # Cấu hình bản đồ (Center ở Cần Thơ là chuẩn rồi)
    settings_overrides = {
       'DEFAULT_CENTER': (10.0452, 105.7469),
       'DEFAULT_ZOOM': 13, # Zoom 13 nhìn rõ phố phường hơn 12 một chút
    }

    inlines = [StoreImageInline]

# --- 4. QUẢN LÝ DUYỆT BÀI ---
class ApprovalProfileAdmin(admin.ModelAdmin):
    list_display = ('store', 'submitter', 'status', 'date_up', 'approver')
    list_filter = ('status', 'date_up')
    search_fields = ('store__name', 'submitter__username') # Tìm theo tên quán hoặc tên user
    
    # Sắp xếp bài mới nhất lên đầu
    ordering = ('-date_up',)

# --- ĐĂNG KÝ ---
admin.site.register(Category, CategoryAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(ApprovalProfile, ApprovalProfileAdmin)

# Không cần register StoreImage riêng lẻ nữa vì nó đã nằm trong Store rồi