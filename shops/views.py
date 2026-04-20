import json
import os
import tempfile
import time

from django.db import transaction
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_gis.filters import InBBoxFilter
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
import requests

from .utils import extract_gps_data
from .models import Store, Category, StoreImage, ApprovalProfile
from .duplicate_checker import check_duplicate
from .serializers import (
    StoreSerializer,
    CategorySerializer,
    StoreImageSerializer,
    ApprovalProfileSerializer
)

ML_SERVER_URL = 'http://localhost:5050'
ML_TIMEOUT    = 300  # seconds — Qwen/AI có thể mất tới vài phút trên CPU


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None


class StoreViewSet(viewsets.ModelViewSet):
    serializer_class = StoreSerializer
    pagination_class = None
    filter_backends  = [InBBoxFilter, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    bbox_filter_field  = 'location'
    filterset_fields   = ['category', 'state']
    search_fields      = ['name', 'address', 'describe']
    ordering_fields    = ['rating_avg', 'rating_count', 'name']

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
    parser_classes     = [MultiPartParser, FormParser]
    filterset_fields   = ['store', 'state']

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class ApprovalProfileViewSet(viewsets.ModelViewSet):
    queryset = ApprovalProfile.objects.all().order_by('-date_up')
    serializer_class   = ApprovalProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields   = ['status', 'store']

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
                profile.status   = 'approved'
                profile.approver = request.user
                profile.save()
            return Response({"message": "Đã duyệt!"})
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        profile = self.get_object()
        if profile.status != 'pending':
            return Response({"error": "Đã xử lý rồi."}, status=400)
        profile.status   = 'rejected'
        profile.approver = request.user
        profile.save()
        return Response({"message": "Đã từ chối."})


# ---------------------------------------------------------------------------
# HELPER: lưu file tạm & trả về path
# ---------------------------------------------------------------------------
def _save_temp_file(file_obj):
    """Lưu InMemoryUploadedFile ra file tạm, trả về đường dẫn."""
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
        for chunk in file_obj.chunks():
            tmp.write(chunk)
        return tmp.name


# ---------------------------------------------------------------------------
# API: Quick Upload  —  Bước 1: Phát hiện biển hiệu (YOLO)
#    POST /api/utils/quick-upload/
#    Body: multipart: image=<file>
#          (optional) box_index=<int>  — nếu truyền thêm, chạy luôn bước 2
# ---------------------------------------------------------------------------
class QuickImageUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes     = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        file_obj = request.FILES.get('image')
        if not file_obj:
            return Response({"error": "No file"}, status=400)

        # ── GPS ──────────────────────────────────────────────────────────────
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        gps_data = extract_gps_data(file_obj) or {}

        # ── Save temp file ───────────────────────────────────────────────────
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        tmp_path = _save_temp_file(file_obj)

        # ── Bước 1: Detect signs ─────────────────────────────────────────────
        detect_result = {}
        try:
            t0 = time.time()
            resp = requests.post(
                f'{ML_SERVER_URL}/detect-signs',
                json={'image_path': tmp_path},
                timeout=ML_TIMEOUT
            )
            write_time = time.time() - t0
            print(f"📸 [MEASURE] /detect-signs: {write_time*1000:.1f} ms")

            if resp.status_code == 200:
                detect_result = resp.json()
            else:
                print(f"DEBUG: /detect-signs lỗi {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"DEBUG: Exception khi /detect-signs: {e}")

        signs = detect_result.get('signs', [])

        # Nếu nhiều biển hiệu (> 1 conf > 70%), trả về để frontend hiển thị UI chọn
        # Chưa xóa file tạm vì bước 2 sẽ dùng lại
        if len(signs) > 1:
            # Lưu tmp_path vào một token phía server KHÔNG cần thiết vì
            # front-end sẽ gửi lại box_index và file; nhưng để đơn giản ta
            # trả về thông tin ảnh crop nhỏ base64 của mỗi biển hiệu để hiển thị
            import cv2
            import numpy as np
            from PIL import Image as PILImage, ImageOps as PILImageOps

            try:
                pil_img = PILImageOps.exif_transpose(PILImage.open(tmp_path))
                frame   = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception:
                frame = cv2.imdecode(np.fromfile(tmp_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

            sign_previews = []
            for s in signs:
                x1, y1, x2, y2 = s['coords']
                crop = frame[max(0, y1):y2, max(0, x1):x2]
                # Encode thumbnail (max 200px wide)
                h_c, w_c = crop.shape[:2]
                if w_c > 200:
                    scale = 200 / w_c
                    crop  = cv2.resize(crop, (200, int(h_c * scale)))
                _, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 70])
                b64    = __import__('base64').b64encode(buf).decode('utf-8')
                sign_previews.append({
                    "index":    s['index'],
                    "conf":     s['conf'],
                    "conf_pct": s['conf_pct'],
                    "preview":  f"data:image/jpeg;base64,{b64}",
                })

            # Trả về để frontend yêu cầu admin chọn
            return Response({
                "gps": {
                    "latitude":    gps_data.get('latitude'),
                    "longitude":   gps_data.get('longitude'),
                    "address_gps": gps_data.get('address', ''),
                },
                "multiple_signs": True,
                "signs":          sign_previews,
                # tmp_path để dùng lại ở bước 2 (gọi /api/utils/analyze-sign/)
                "tmp_path":       tmp_path,
            })

        # ── Nếu chỉ 1 (hoặc 0) biển hiệu: chạy thẳng bước 2 ─────────────────
        ml_data = {}
        try:
            box_index = int(request.data.get('box_index', 0))
            t0 = time.time()
            resp = requests.post(
                f'{ML_SERVER_URL}/analyze',
                json={'image_path': tmp_path, 'box_index': box_index},
                timeout=ML_TIMEOUT
            )
            print(f"📸 [MEASURE] /analyze: {(time.time()-t0)*1000:.1f} ms")
            if resp.status_code == 200:
                ml_data = resp.json()
            else:
                print(f"DEBUG: /analyze lỗi {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"DEBUG: Exception khi /analyze: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return Response(_build_ocr_response(gps_data, ml_data))


# ---------------------------------------------------------------------------
# API: Analyze chosen sign  —  Bước 2 (khi admin đã chọn biển hiệu)
#    POST /api/utils/analyze-sign/
#    Body JSON: { "tmp_path": "...", "box_index": 0 }
# ---------------------------------------------------------------------------
class AnalyzeSignView(APIView):
    parser_classes         = [JSONParser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes     = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        tmp_path  = request.data.get('tmp_path')
        box_index = int(request.data.get('box_index', 0))

        if not tmp_path or not os.path.exists(tmp_path):
            return Response({"error": "tmp_path không tồn tại. Vui lòng tải lại ảnh."}, status=400)

        ml_data = {}
        try:
            t0 = time.time()
            resp = requests.post(
                f'{ML_SERVER_URL}/analyze',
                json={'image_path': tmp_path, 'box_index': box_index},
                timeout=ML_TIMEOUT
            )
            print(f"📸 [MEASURE] /analyze (chosen sign): {(time.time()-t0)*1000:.1f} ms")
            if resp.status_code == 200:
                ml_data = resp.json()
            else:
                print(f"DEBUG: /analyze lỗi {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"DEBUG: Exception khi /analyze: {e}")

        # KHÔNG xóa tmp_path — giữ lại để người dùng có thể đổi sang biển hiệu khác.
        # File sẽ được xóa qua endpoint /utils/cleanup-tmp/ hoặc tự hết hạn bởi OS.
        result = _build_ocr_response({}, ml_data)
        result['tmp_path'] = tmp_path  # trả về để frontend dùng tiếp
        return Response(result)


def normalize_phone(raw):
    """
    Chuẩn hóa một số điện thoại Việt Nam về dạng 0xxxxxxxxx hoặc giữ nguyên nếu không nhận dạng được.
    +84xxxxxxxxx → 0xxxxxxxxx
    84xxxxxxxxx  → 0xxxxxxxxx
    """
    import re
    if not raw:
        return None
    digits = re.sub(r'[^\d+]', '', str(raw).strip())
    if digits.startswith('+84'):
        digits = '0' + digits[3:]
    elif digits.startswith('84') and len(digits) >= 10:
        digits = '0' + digits[2:]
    # Kiểm tra độ dài hợp lệ: 10–11 chữ số bắt đầu bằng 0
    if re.match(r'^0\d{8,10}$', digits):
        return digits
    # Hotline 1800/1900: giữ nguyên
    if re.match(r'^(1[89]00\d{4})$', digits):
        return digits
    return None


def merge_phones(phone_list):
    """
    Nhận list số thô, chuẩn hóa từng số và gộp lại thành chuỗi ngăn cách ' | '.
    Bỏ qua số không hợp lệ và loại trùng lặp.
    """
    seen = []
    for p in phone_list:
        # Cho phép chuỗi đã có ' | ' bên trong (ví dụ từ DB gửi lại)
        for part in str(p).split('|'):
            normalized = normalize_phone(part.strip())
            if normalized and normalized not in seen:
                seen.append(normalized)
    return seen


def _build_ocr_response(gps_data, ml_data):
    """Tổng hợp response thống nhất từ dữ liệu GPS và ML."""
    category_name = ml_data.get('category', '')
    category_id   = None
    if category_name:
        cat = Category.objects.filter(name__icontains=category_name).first()
        if cat:
            category_id = cat.id

    info      = ml_data.get('info', {})
    extracted = ml_data.get('extracted', {})   # Chứa BRAND, SERVICE, ADDRESS, PHONE, O

    # Chuẩn hóa + gộp nhiều số điện thoại thành chuỗi chuẩn
    raw_phones   = info.get('phone', [])
    normalized_phones = merge_phones(raw_phones)  # Trả về mảng các số đã chuẩn hóa

    return {
        "latitude":    gps_data.get('latitude'),
        "longitude":   gps_data.get('longitude'),
        "address_gps": gps_data.get('address', ''),
        "category_id": category_id,
        "contact_info": {
            "brand":   info.get('brand',   []),
            "service": info.get('service', []),
            "address": info.get('address', []),
            "phone":   normalized_phones,   # ← trả về list để JS xử lý linh hoạt
            "email":   info.get('email',   []),
            "website": info.get('website', []),
            # Thông tin phụ / không liên quan (slogan, chứng chỉ, quảng cáo...)
            # → gợi ý thêm vào phần mô tả
            "other":   extracted.get('O',  []),
        },
        "raw_texts": ml_data.get('texts', []),
        "multiple_signs": False,
    }



class AnalyzeImageView(APIView):
    """API cũ, giữ lại để tương thích."""
    parser_classes     = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]

    def post(self, request, format=None):
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({"error": "No file"}, status=400)
        result = extract_gps_data(image_file)
        return Response(result if result else {"warning": "No GPS"}, status=200)


# ---------------------------------------------------------------------------
# API: Kiểm tra trùng cửa hàng  — Pipeline 5 bước
#    POST /api/utils/check-duplicate/
#    Body JSON: { "name": "...", "lat": 10.xxx, "lng": 105.xxx }
# ---------------------------------------------------------------------------
class CheckDuplicateView(APIView):
    """
    Kiểm tra trùng tên cửa hàng trong bán kính 15 mét xung quanh tọa độ.
    Pipeline:
      1. Normalize text (lowercase, remove accent, regex clean)
      2. Retrieve candidates (PostGIS ST_DWithin 15m)
      3. Compute similarity (partial_ratio, token_set_ratio, levenshtein)
      4. Aggregate score (weighted)
      5. Decision (accept / warning / reject)
    """
    parser_classes         = [JSONParser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes     = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        name = request.data.get('name', '').strip()
        try:
            lat = float(request.data.get('lat'))
            lng = float(request.data.get('lng'))
        except (TypeError, ValueError):
            return Response(
                {"decision": "accept", "matches": [], "info": "Tọa độ không hợp lệ — bỏ qua kiểm tra vị trí."},
                status=200
            )

        if not name:
            return Response({"decision": "accept", "matches": []}, status=200)

        result = check_duplicate(name, lat, lng, radius_m=15.0)
        return Response(result, status=200)