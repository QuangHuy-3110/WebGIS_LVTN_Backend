from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'categories',   views.CategoryViewSet,       basename='category')
router.register(r'stores',       views.StoreViewSet,          basename='store')
router.register(r'store-images', views.StoreImageViewSet,     basename='store-image')
router.register(r'approvals',    views.ApprovalProfileViewSet, basename='approval')

urlpatterns = [
    path('utils/quick-upload/',     views.QuickImageUploadView.as_view(),  name='quick-upload'),
    path('utils/analyze-sign/',     views.AnalyzeSignView.as_view(),       name='analyze-sign'),
    path('utils/analyze-image/',    views.AnalyzeImageView.as_view(),      name='analyze-image'),
    path('utils/check-duplicate/',  views.CheckDuplicateView.as_view(),    name='check-duplicate'),
    path('', include(router.urls)),
]