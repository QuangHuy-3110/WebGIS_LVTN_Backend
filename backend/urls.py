"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# --- CẤU HÌNH GIAO DIỆN ADMIN ---
admin.site.site_header = "Hệ thống Quản lý Bản đồ GIS"
admin.site.site_title = "GIS Admin Portal"
admin.site.index_title = "Dashbord"

urlpatterns = [
    # 1. Trang quản trị Django
    path('admin/', admin.site.urls),

    # 2. APP USERS
    path('api/', include('users.urls')),

    # 3. APP SHOPS
    path('api/', include('shops.urls')),
    
    # 4. APP SOCIAL
    path('api/', include('social.urls')),

    # --- 5. APP API (Thêm dòng này để nạp RoutingView) ---
    # Đường dẫn sẽ là: /api/route/
    path('api/', include('api.urls')), 
]

# --- CẤU HÌNH MEDIA ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)