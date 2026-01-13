from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, SearchHistory

# 1. CUSTOM JWT SERIALIZER
# Dùng để login, trả về token kèm theo thông tin user
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Thêm thông tin tùy chỉnh vào response trả về sau khi login thành công
        data['user_id'] = self.user.id
        data['username'] = self.user.username
        data['full_name'] = self.user.full_name
        data['role'] = self.user.role      # Quan trọng để phân quyền ở frontend
        data['is_staff'] = self.user.is_staff 
        
        # Trả về URL avatar nếu có
        if self.user.avatar:
            data['avatar'] = self.user.avatar.url
        else:
            data['avatar'] = None
            
        return data

# 2. USER SERIALIZER
# Dùng để đăng ký, xem profile, cập nhật thông tin
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'first_name', 'last_name', 'full_name', 'email', 'phone', 'role', 'avatar']
        extra_kwargs = {
            'password': {'write_only': True}, # Chỉ cho phép ghi (đăng ký), không trả về khi xem
            'avatar': {'read_only': True},    # Avatar nên upload qua API riêng hoặc form-data
        }

    def create(self, validated_data):
        # Override hàm create để mã hóa mật khẩu (hash password)
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)
        if password is not None:
            instance.set_password(password) # Hàm này của Django giúp hash password
        instance.save()
        return instance

# 3. SEARCH HISTORY SERIALIZER
# Dùng để lưu và xem lịch sử tìm kiếm
class SearchHistorySerializer(serializers.ModelSerializer):
    # Format ngày tháng thành dạng dd/mm/yyyy cho dễ đọc
    create_at = serializers.DateField(format="%d/%m/%Y", read_only=True)
    
    class Meta:
        model = SearchHistory
        fields = ['id', 'user', 'keyword', 'search_location', 'create_at']
        read_only_fields = ['user', 'create_at']