from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_gis.filters import InBBoxFilter  # Cần thiết cho bản đồ

from .models import Store, Category, StoreImage, ApprovalProfile
from .serializers import (
    StoreSerializer, 
    CategorySerializer, 
    StoreImageSerializer, 
    ApprovalProfileSerializer
)

# 1. Quản lý Danh mục (Category)
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None  # Danh mục thường ít, có thể tắt phân trang để load hết vào combobox

# 2. Quản lý Cửa hàng (Store)
class StoreViewSet(viewsets.ModelViewSet):
    """
    API endpoint cho Cửa hàng.
    Hỗ trợ tìm kiếm không gian (Bản đồ), tìm kiếm text và lọc theo danh mục.
    """
    serializer_class = StoreSerializer
    
    # Lưu ý: Trong Model, 'state' là CharField (ví dụ: 'active', 'closed').
    # Nếu muốn chỉ lấy quán đang mở, hãy filter theo string cụ thể.
    queryset = Store.objects.all().order_by('-rating_avg')

    filter_backends = [
        InBBoxFilter,           # Lọc theo khung nhìn bản đồ (?in_bbox=minlon,minlat,maxlon,maxlat)
        DjangoFilterBackend,    # Lọc chính xác (?category=1)
        filters.SearchFilter,   # Tìm kiếm text (?search=abc)
        filters.OrderingFilter  # Sắp xếp (?ordering=rating_avg)
    ]
    
    # Cấu hình field cho BBoxFilter (trường hình học trong model)
    bbox_filter_field = 'location' 

    # Cấu hình field để lọc (DjangoFilterBackend)
    filterset_fields = ['category', 'state'] 
    
    # Cấu hình field để tìm kiếm (SearchFilter)
    search_fields = ['name', 'address', 'describe']
    
    # Cấu hình field để sắp xếp (OrderingFilter)
    # Lưu ý: Model Store của bạn không có 'created_at', nên tôi đã bỏ đi để tránh lỗi
    ordering_fields = ['rating_avg', 'rating_count', 'name']


# 3. Quản lý Ảnh cửa hàng (StoreImage)
class StoreImageViewSet(viewsets.ModelViewSet):
    queryset = StoreImage.objects.all().order_by('-time_up')
    serializer_class = StoreImageSerializer
    filter_backends = [DjangoFilterBackend]
    
    # Quan trọng: Cho phép lọc ảnh theo store (?store=1)
    filterset_fields = ['store', 'uploaded_by', 'state']


# 4. Quản lý Hồ sơ duyệt (ApprovalProfile)
class ApprovalProfileViewSet(viewsets.ModelViewSet):
    queryset = ApprovalProfile.objects.all().order_by('-date_up')
    serializer_class = ApprovalProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    
    # Lọc theo trạng thái duyệt, người gửi, người duyệt, hoặc theo store
    filterset_fields = ['status', 'submitter', 'approver', 'store']
    
    ordering_fields = ['date_up', 'date_sign']

    # Gợi ý: Nếu muốn override hàm create để tự động gán user hiện tại làm người submit
    def perform_create(self, serializer):
        # Nếu user đã đăng nhập, gán vào field submitter
        if self.request.user.is_authenticated:
            serializer.save(submitter=self.request.user)
        else:
            serializer.save()