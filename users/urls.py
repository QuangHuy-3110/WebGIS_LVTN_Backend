from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView

from . import views
from .serializers import MyTokenObtainPairSerializer

# --- TẠO VIEW LOGIN CUSTOM ---
# (Để sử dụng Serializer custom bạn đã viết, giúp trả về thêm role/avatar khi login)
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

# --- CẤU HÌNH ROUTER ---
router = DefaultRouter()

# 1. API Quản lý User (Đăng ký, Profile, Update)
router.register(r'users', views.UserViewSet, basename='user')

# 2. API Lịch sử tìm kiếm
router.register(r'search-history', views.SearchHistoryViewSet, basename='search-history')

urlpatterns = [
    # Include các URL do router tạo ra (CRUD user, history)
    path('', include(router.urls)),

    # API Cập nhật thông tin cá nhân (Avatar, tên...)
    path('profile/update/', views.UserProfileView.as_view(), name='profile-update'),
    
    # API Đổi mật khẩu
    path('profile/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    
    # --- API XÁC THỰC (AUTH) ---
    # Login: Trả về Access Token + Refresh Token + Info User
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    
    # Refresh: Lấy token mới khi token cũ hết hạn
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]