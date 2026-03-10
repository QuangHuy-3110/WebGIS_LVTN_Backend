import json
from django.db import transaction
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_gis.filters import InBBoxFilter
from rest_framework.views import APIView
# --- THÊM DÒNG NÀY ĐỂ FIX LỖI 401 ---
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
import requests

# ------------------------------------
from .utils import extract_gps_data

from .models import Store, Category, StoreImage, ApprovalProfile
from .serializers import (
    StoreSerializer, 
    CategorySerializer, 
    StoreImageSerializer, 
    ApprovalProfileSerializer
)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None

class StoreViewSet(viewsets.ModelViewSet):
    serializer_class = StoreSerializer
    pagination_class = None
    filter_backends = [InBBoxFilter, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    bbox_filter_field = 'location' 
    filterset_fields = ['category', 'state'] 
    search_fields = ['name', 'address', 'describe']
    ordering_fields = ['rating_avg', 'rating_count', 'name']

    def get_queryset(self):
        queryset = Store.objects.all().order_by('-rating_avg')
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(state='active')

    def perform_create(self, serializer):
        serializer.save(state='pending', is_active=False)

class StoreImageViewSet(viewsets.ModelViewSet):
    queryset = StoreImage.objects.all()
    serializer_class = StoreImageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser] 
    filterset_fields = ['store', 'state']

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

class ApprovalProfileViewSet(viewsets.ModelViewSet):
    queryset = ApprovalProfile.objects.all().order_by('-date_up')
    serializer_class = ApprovalProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'store']

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user, status='pending')

    def perform_update(self, serializer):
        serializer.save(approver=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        profile = self.get_object()
        if profile.status != 'pending':
            return Response({"error": "Đã xử lý rồi."}, status=400)
        try:
            with transaction.atomic():
                changes = json.loads(profile.note)
                # Logic xử lý approve (giả lập)
                profile.status = 'approved'
                profile.approver = request.user
                profile.save()
            return Response({"message": "Đã duyệt!"})
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        profile = self.get_object()
        if profile.status != 'pending': return Response({"error": "Đã xử lý rồi."}, status=400)
        profile.status = 'rejected'
        profile.approver = request.user
        profile.save()
        return Response({"message": "Đã từ chối."})

# --- API UPLOAD NHANH (QUAN TRỌNG) ---
class QuickImageUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    # Cho phép Admin dùng Cookie để gọi API này (Tránh lỗi 401)
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        file_obj = request.FILES.get('image')
        if not file_obj:
            return Response({"error": "No file"}, status=400)

        # 1. Reset file để đọc GPS
        if hasattr(file_obj, 'seek'): file_obj.seek(0)
        gps_data = extract_gps_data(file_obj) or {}

        # 2. Reset file lần nữa để Django lưu
        if hasattr(file_obj, 'seek'): file_obj.seek(0)

        # 3. Lưu ảnh "mồ côi" (Store=None)
        temp_img = StoreImage.objects.create(
            image=file_obj,
            uploaded_by=request.user,
            store=None,
            state='private'
        )

        # Call ML Server to analyze the uploaded image
        ml_data = {}
        try:
            image_abs_path = temp_img.image.path
            print(f"DEBUG: Gửi ảnh cho ML Model: {image_abs_path}")
            resp = requests.post('http://localhost:5050/analyze', json={'image_path': image_abs_path}, timeout=60)
            if resp.status_code == 200:
                ml_data = resp.json()
                print(f"DEBUG: Nhận dc ML_DATA: {ml_data}")
            else:
                print(f"DEBUG: Lỗi từ ML_Server: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"DEBUG: Exception khi request ML: {e}")

        category_name = ml_data.get('category', '')
        category_id = None
        if category_name:
            cat = Category.objects.filter(name__icontains=category_name).first()
            if cat:
                category_id = cat.id

        return Response({
            "id": temp_img.id,
            "url": temp_img.image.url,
            "latitude": gps_data.get('latitude'),
            "longitude": gps_data.get('longitude'),
            "address_gps": gps_data.get('address', ''),
            "category_id": category_id,
            "contact_info": ml_data.get('info', {}),
            "raw_texts": ml_data.get('texts', [])
        })

class AnalyzeImageView(APIView):
    # API cũ, giữ lại để tương thích nếu cần
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]
    def post(self, request, format=None):
        image_file = request.FILES.get('image')
        if not image_file: return Response({"error": "No file"}, status=400)
        result = extract_gps_data(image_file)
        return Response(result if result else {"warning": "No GPS"}, status=200)