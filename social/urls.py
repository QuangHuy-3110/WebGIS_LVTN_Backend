from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Tạo router
router = DefaultRouter()

# Đăng ký các ViewSet của app Social
router.register(r'reviews', views.ReviewViewSet, basename='review')
router.register(r'favorites', views.FavoriteViewSet, basename='favorite')

# Bắt buộc phải có biến urlpatterns
urlpatterns = [
    path('', include(router.urls)),
]