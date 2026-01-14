from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Review, Favorite
from .serializers import ReviewSerializer, FavoriteSerializer

# --- CUSTOM PERMISSION ---
class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Cho phép mọi người xem (GET, HEAD, OPTIONS).
    Nhưng chỉ CHỦ SỞ HỮU mới được sửa (PUT) hoặc xóa (DELETE).
    """
    def has_object_permission(self, request, view, obj):
        # Các method an toàn (xem) thì luôn cho phép
        if request.method in permissions.SAFE_METHODS:
            return True
        # Nếu sửa/xóa, phải là chủ sở hữu (obj.user)
        return obj.user == request.user

# --- VIEWS ---

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all().order_by('-created_at') # Review mới nhất lên đầu
    serializer_class = ReviewSerializer
    
    # IsAuthenticatedOrReadOnly: Chưa đăng nhập chỉ được xem. Đăng nhập rồi được post.
    # IsOwnerOrReadOnly: Chỉ được sửa/xóa bài của chính mình.
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    
    # Lọc review theo quán (?store=1) hoặc theo người dùng (?user=5)
    filterset_fields = ['store', 'user', 'rating']
    
    ordering_fields = ['rating', 'created_at']

    def perform_create(self, serializer):
        # Tự động gán user hiện tại là người viết review
        serializer.save(user=self.request.user)


class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated] # Bắt buộc phải đăng nhập
    queryset = Favorite.objects.all().order_by('-id')
    # Chỉ cho phép: Xem, Thêm, Xóa (Không cho sửa - PUT/PATCH vì không cần thiết)
    http_method_names = ['get', 'post', 'delete', 'head']

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['store'] # Lọc xem user có thích quán X không

    def get_queryset(self):
        # Chỉ trả về danh sách yêu thích CỦA NGƯỜI DÙNG ĐANG ĐĂNG NHẬP
        # Người dùng A không nên thấy danh sách yêu thích của người dùng B
        # return Favorite.objects.filter(user=self.request.user).order_by('-id')
        return Favorite.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)