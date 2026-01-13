"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# --- CẤU HÌNH GIAO DIỆN ADMIN (Giữ nguyên phần bạn đã làm rất tốt) ---
admin.site.site_header = "Hệ thống Quản lý Bản đồ GIS"
admin.site.site_title = "GIS Admin Portal"
admin.site.index_title = "Chào mừng đến với trang quản trị"

urlpatterns = [
    # 1. Trang quản trị Django
    path('admin/', admin.site.urls),

    # 2. APP USERS (Bao gồm cả Login, Register, Profile, Lịch sử)
    # Nó sẽ chứa các link: /api/users/, /api/token/, /api/search-history/
    path('api/', include('users.urls')),

    # 3. APP SHOPS (Bao gồm Store, Category, Map, Approval)
    # Nó sẽ chứa các link: /api/stores/, /api/categories/, ...
    path('api/', include('shops.urls')),
    
    # 4. APP SOCIAL (Bao gồm Review, Favorite) - Nếu bạn đã tạo file urls.py cho social
    # Nó sẽ chứa các link: /api/reviews/, /api/favorites/
    path('api/', include('social.urls')),
]

# --- CẤU HÌNH MEDIA (DEBUG MODE) ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)