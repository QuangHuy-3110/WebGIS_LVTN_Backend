from rest_framework import viewsets, generics,permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser # Để upload avatar
from .serializers import UserUpdateSerializer, ChangePasswordSerializer
from django.contrib.auth import get_user_model

from .models import User, SearchHistory
from .serializers import UserSerializer, SearchHistorySerializer

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    parser_classes = [MultiPartParser, FormParser] # Hỗ trợ upload ảnh avatar

    def get_permissions(self):
        # Cho phép bất kỳ ai cũng có thể Đăng ký (POST)
        if self.action == 'create':
            return [permissions.AllowAny()]
        # Các hành động khác (Xem, Sửa) cần phải đăng nhập
        return [permissions.IsAuthenticated()]

    def get_object(self):
        # Override hàm này để đảm bảo User chỉ có thể sửa/xem profile của CHÍNH MÌNH
        # (Trừ khi là Admin thì logic sẽ khác, ở đây làm đơn giản cho App)
        return self.request.user

    # API đặc biệt: GET /api/users/current-user/
    # Giúp frontend lấy thông tin user đang đăng nhập hiện tại
    @action(detail=False, methods=['get'], url_path='current-user')
    def current_user(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

class SearchHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = SearchHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # QUAN TRỌNG: Chỉ trả về lịch sử của người đang đăng nhập
        return SearchHistory.objects.filter(user=self.request.user).order_by('-create_at')

    def perform_create(self, serializer):
        # Tự động gán user hiện tại vào bản ghi lịch sử
        serializer.save(user=self.request.user)

User = get_user_model()

class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserUpdateSerializer

    def get_object(self):
        return self.request.user

class ChangePasswordView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def update(self, request, *args, **kwargs):
        user = self.request.user
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check password cũ
            if not user.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Mật khẩu cũ không đúng."]}, status=status.HTTP_400_BAD_REQUEST)
            
            # Set password mới
            user.set_password(serializer.data.get("new_password"))
            user.save()
            return Response({"message": "Đổi mật khẩu thành công!"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)