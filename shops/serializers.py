from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Store, Category, StoreImage, ApprovalProfile

# 1. Category Serializer
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']

# 2. Store Image Serializer
class StoreImageSerializer(serializers.ModelSerializer):
    # Model dùng 'describe', không phải 'caption' nên cần sửa lại cho khớp
    class Meta:
        model = StoreImage
        fields = ['id', 'image', 'describe', 'uploaded_by', 'state', 'time_up']

# 3. Store Serializer (GeoJSON)
class StoreSerializer(GeoFeatureModelSerializer):
    category_detail = CategorySerializer(source='category', read_only=True)
    
    # Quan trọng: Trong Model StoreImage bạn đặt related_name="image" (số ít)
    # nên ở đây phải khai báo source='image' để Django hiểu.
    images = StoreImageSerializer(many=True, read_only=True, source='image')

    class Meta:
        model = Store
        fields = [
            'id', 
            'name', 
            'address', 
            'phone',       # Thêm field từ model
            'email',       # Thêm field từ model
            'category', 
            'category_detail', 
            'rating_avg', 
            'rating_count', # Thêm field từ model
            'open_time', 
            'close_time', 
            'state', 
            'describe',    # Thêm field từ model
            'location', 
            'images'
        ]
        geo_field = 'location'

# 4. Approval Profile Serializer (Mới)
class ApprovalProfileSerializer(serializers.ModelSerializer):
    # Hiển thị thêm tên để Frontend dễ hiển thị thay vì chỉ hiện ID
    store_name = serializers.CharField(source='store.name', read_only=True)
    submitter_name = serializers.CharField(source='submitter.username', read_only=True)
    approver_name = serializers.CharField(source='approver.username', read_only=True)

    class Meta:
        model = ApprovalProfile
        fields = [
            'id', 
            'store', 
            'store_name',      # Field đọc thêm
            'submitter', 
            'submitter_name',  # Field đọc thêm
            'approver', 
            'approver_name',   # Field đọc thêm
            'status', 
            'date_up', 
            'date_sign', 
            'note'
        ]
        read_only_fields = ['date_up', 'date_sign']