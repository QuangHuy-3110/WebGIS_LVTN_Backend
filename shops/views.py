import json
from django.db import transaction # Để đảm bảo an toàn dữ liệu
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_gis.filters import InBBoxFilter
from rest_framework.views import APIView
from .utils import extract_gps_data

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
    pagination_class = None

# 2. Quản lý Cửa hàng (Store)
class StoreViewSet(viewsets.ModelViewSet):
    """
    API endpoint cho Cửa hàng.
    Hỗ trợ tìm kiếm không gian (Bản đồ), tìm kiếm text và lọc theo danh mục.
    """
    serializer_class = StoreSerializer
    pagination_class = None

    # Các bộ lọc (Giữ nguyên)
    filter_backends = [
        InBBoxFilter,           
        DjangoFilterBackend,    
        filters.SearchFilter,   
        filters.OrderingFilter  
    ]
    
    bbox_filter_field = 'location' 
    filterset_fields = ['category', 'state'] 
    search_fields = ['name', 'address', 'describe']
    ordering_fields = ['rating_avg', 'rating_count', 'name']

    # --- 1. SỬA LOGIC LẤY DỮ LIỆU ---
    def get_queryset(self):
        # Lấy tất cả cửa hàng
        queryset = Store.objects.all().order_by('-rating_avg')

        # 1. Nếu là Admin: Xem được tất cả (Active, Pending, Rejected...)
        if self.request.user.is_staff:
            return queryset
        
        # 2. Nếu là User thường/Khách: Chỉ xem cửa hàng có state='active'
        # --- SỬA DÒNG NÀY ---
        return queryset.filter(state='active')
        # --------------------

    def perform_create(self, serializer):
        # Khi tạo mới: state='pending', is_active=False
        serializer.save(state='pending', is_active=False)

# 3. Quản lý Hình ảnh (StoreImage)
class StoreImageViewSet(viewsets.ModelViewSet):
    queryset = StoreImage.objects.all()
    serializer_class = StoreImageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    # BẮT BUỘC PHẢI CÓ ĐỂ UPLOAD ẢNH
    parser_classes = [MultiPartParser, FormParser] 
    
    filterset_fields = ['store', 'state']

    def perform_create(self, serializer):
        # 1. uploaded_by: Lấy từ user đang đăng nhập (self.request.user)
        # 2. state: Mặc định là 'private' (nếu frontend không gửi)
        # 3. describe: Lấy từ dữ liệu frontend gửi lên
        # 4. time_up: Tự động do model auto_now_add=True
        serializer.save(uploaded_by=self.request.user)

# 4. Quản lý Hồ sơ duyệt (ApprovalProfile)
class ApprovalProfileViewSet(viewsets.ModelViewSet):
    queryset = ApprovalProfile.objects.all().order_by('-date_up')
    serializer_class = ApprovalProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'store']

    # Tự động gán người tạo
    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user, status='pending')

    # Trong ApprovalProfileViewSet
    def perform_update(self, serializer):
        # Chỉ cần lưu thôi, Signal bên models.py sẽ tự lo phần còn lại
        serializer.save(approver=self.request.user)

    # API riêng: POST /api/approvals/{id}/approve/
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        profile = self.get_object()
        
        if profile.status != 'pending':
            return Response({"error": "Hồ sơ này đã được xử lý rồi."}, status=400)

        try:
            with transaction.atomic():
                changes = json.loads(profile.note)
                
                # Gọi hàm xử lý chung
                self._process_approval(profile, changes)

                # Cập nhật trạng thái hồ sơ
                profile.status = 'approved'
                profile.approver = request.user
                profile.save()

            return Response({"message": "Đã duyệt hồ sơ và cập nhật cửa hàng!"})

        except json.JSONDecodeError:
            return Response({"error": "Lỗi dữ liệu note không phải JSON hợp lệ"}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    # API riêng: POST /api/approvals/{id}/reject/
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        profile = self.get_object()
        if profile.status != 'pending':
            return Response({"error": "Hồ sơ này đã được xử lý rồi."}, status=400)
            
        profile.status = 'rejected'
        profile.approver = request.user
        profile.save()
        
        return Response({"message": "Đã từ chối hồ sơ."})
    
class AnalyzeImageView(APIView):
    """
    API hỗ trợ: Nhận file ảnh -> Trả về GPS và Địa chỉ.
    Dùng để auto-fill form khi tạo cửa hàng mới.
    """
    parser_classes = [MultiPartParser, FormParser] # Để nhận được file upload
    permission_classes = [permissions.AllowAny] # Hoặc IsAuthenticated tuỳ bạn

    def post(self, request, format=None):
        image_file = request.FILES.get('image')
        
        if not image_file:
            return Response({"error": "Không tìm thấy file ảnh"}, status=400)

        # Gọi hàm xử lý từ utils
        result = extract_gps_data(image_file)

        if result:
            return Response(result, status=200)
        else:
            return Response(
                {"warning": "Ảnh không có dữ liệu GPS hoặc lỗi xử lý"}, 
                status=200
            )