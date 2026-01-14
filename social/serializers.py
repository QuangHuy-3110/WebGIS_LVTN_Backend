from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from .models import Review, Favorite

class ReviewSerializer(serializers.ModelSerializer):
    # Hiển thị tên người dùng thay vì chỉ hiện ID
    user_name = serializers.CharField(source='user.username', read_only=True)
    # Nếu User model có field avatar, bạn có thể thêm vào đây:
    # user_avatar = serializers.ImageField(source='user.avatar', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user', 'user_name', 'store', 'rating', 'content', 'created_at']
        read_only_fields = ['user', 'created_at'] # User tự động lấy từ request, không cho sửa

    def validate_rating(self, value):
        # Đảm bảo điểm đánh giá hợp lệ (1-5)
        if value < 1 or value > 5:
            raise serializers.ValidationError("Điểm đánh giá phải từ 1 đến 5.")
        return value

class FavoriteSerializer(serializers.ModelSerializer):
    # Hiển thị thêm tên quán để khi xem danh sách yêu thích sẽ dễ nhìn hơn
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    store_name = serializers.CharField(source='store.name', read_only=True)
    store_address = serializers.CharField(source='store.address', read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'user', 'store', 'store_name', 'store_address']
        # read_only_fields = ['user']

        # Validator này giúp trả về lỗi rõ ràng nếu user thích 1 quán 2 lần
        validators = [
            UniqueTogetherValidator(
                queryset=Favorite.objects.all(),
                fields=['user', 'store'],
                message="Bạn đã thêm quán này vào danh sách yêu thích rồi."
            )
        ]