from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Store, Category, StoreImage, ApprovalProfile

# 1. Serializer cho Category (Để lấy Icon)
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'icon']

# 2. Serializer cho Store Image (BẮT BUỘC PHẢI CÓ ĐỂ TRÁNH LỖI IMPORT)
class StoreImageSerializer(serializers.ModelSerializer):
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.all())
    uploaded_by_name = serializers.ReadOnlyField(source='uploaded_by.username')
    state = serializers.CharField(required=False, default='private')

    class Meta:
        model = StoreImage
        read_only_fields = ['time_up', 'uploaded_by', 'state', 'uploaded_by_name']
        fields = [
            'id', 'store', 'image', 'describe', 
            'uploaded_by', 'uploaded_by_name', 
            'state', 'time_up'
        ]

# 3. Serializer cho Store (Đã có category_detail)
class StoreSerializer(GeoFeatureModelSerializer):
    # Dòng này giúp lấy icon:
    category_detail = CategorySerializer(source='category', read_only=True)
    
    images = serializers.SerializerMethodField()
    open_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    close_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    image = serializers.ImageField(write_only=True, required=False)

    email = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'address', 'phone', 'email', 
            'category', 
            'category_detail', # <--- Bắt buộc phải có
            'rating_avg', 'rating_count', 
            'open_time', 'close_time', 
            'state', 'describe', 'location', 
            'images', 'image'
        ]
        geo_field = 'location'
        read_only_fields = ['rating_avg', 'rating_count', 'is_active']

    def get_images(self, obj):
        public_images = obj.image.filter(state='public')
        return StoreImageSerializer(public_images, many=True, context=self.context).data

    def create(self, validated_data):
        image_data = validated_data.pop('image', None)
        store = Store.objects.create(**validated_data)
        if image_data:
            request = self.context.get('request')
            user = request.user if request else None
            StoreImage.objects.create(
                store=store, image=image_data, 
                uploaded_by=user, state='private'
            )
        return store

# 4. Serializer cho Approval
class ApprovalProfileSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    approver_name = serializers.CharField(source='approver.username', read_only=True)
    submitter_name = serializers.ReadOnlyField(source='submitter.username')
    
    class Meta:
        model = ApprovalProfile
        fields = '__all__'