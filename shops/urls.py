from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Tạo một router mặc định
router = DefaultRouter()

# Đăng ký các ViewSet vào router
# Cú pháp: router.register(r'tên-đường-dẫn', ViewSet, basename='tên-định-danh')

# 1. API cho Danh mục (VD: /api/categories/)
router.register(r'categories', views.CategoryViewSet, basename='category')

# 2. API cho Cửa hàng (VD: /api/stores/)
router.register(r'stores', views.StoreViewSet, basename='store')

# 3. API cho Ảnh cửa hàng (VD: /api/store-images/)
router.register(r'store-images', views.StoreImageViewSet, basename='store-image')

# 4. API cho Hồ sơ duyệt (VD: /api/approvals/)
router.register(r'approvals', views.ApprovalProfileViewSet, basename='approval')

urlpatterns = [
    path('utils/analyze-image/', views.AnalyzeImageView.as_view(), name='analyze-image'),
    # Include tất cả các đường dẫn do router tự sinh ra
    path('', include(router.urls)),
]