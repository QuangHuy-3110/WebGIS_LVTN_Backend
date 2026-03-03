from django.urls import path
from .views import RoutingView, ExtractGPSView

urlpatterns = [
    # Chỉ chứa đường dẫn tìm đường, không "ôm" các app khác
    path('route/', RoutingView.as_view(), name='internal-routing'),
    path('extract-gps/', ExtractGPSView.as_view(), name='extract-gps'),
]