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
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.all())
    
    # 1. Khai báo trường này
    uploaded_by_name = serializers.ReadOnlyField(source='uploaded_by.username')
    state = serializers.CharField(required=False, default='private')

    class Meta:
        model = StoreImage
        read_only_fields = ['time_up']
        
        # 2. QUAN TRỌNG: Phải thêm 'uploaded_by_name' vào danh sách này
        fields = [
            'id', 
            'store', 
            'image', 
            'describe', 
            'uploaded_by', 
            'uploaded_by_name',  # <--- THÊM DÒNG NÀY
            'state', 
            'time_up'
        ]

        read_only_fields = ['time_up', 'uploaded_by', 'state', 'uploaded_by_name']

# 3. Store Serializer (GeoJSON) - ĐÃ SỬA
class StoreSerializer(GeoFeatureModelSerializer):
    category_detail = CategorySerializer(source='category', read_only=True)
    
    # --- SỬA 1: Dùng MethodField để lọc ảnh Public ---
    # Thay vì: images = StoreImageSerializer(many=True, read_only=True, source='image')
    images = serializers.SerializerMethodField()
    # -------------------------------------------------

    # --- SỬA 2: Fix lỗi Timezone cho giờ mở cửa (Tránh lỗi 500) ---
    open_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    close_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    # --------------------------------------------------------------
    image = serializers.ImageField(write_only=True, required=False)
    class Meta:
        model = Store
        fields = [
            'id', 'name', 'address', 'phone', 'email', 
            'category', 'category_detail', 
            'rating_avg', 'rating_count', 
            'open_time', 'close_time', 
            'state', 'describe', 'location', 
            'images', # Đây là list ảnh hiển thị (read_only)
            'image'   # Đây là file ảnh gửi lên (write_only)
        ]
        geo_field = 'location'
        read_only_fields = ['rating_avg', 'rating_count', 'state', 'is_active']

    # --- HÀM LỌC ẢNH ---
    def get_images(self, obj):
        # Lưu ý: Do bạn đặt related_name='image' (số ít) trong models.py
        # Nên ở đây ta gọi là obj.image (thay vì obj.storeimage_set)
        
        # Chỉ lấy ảnh có state='public'
        public_images = obj.image.filter(state='public')
        
        return StoreImageSerializer(public_images, many=True, context=self.context).data
    # -------------------

    def create(self, validated_data):
        # Tách dữ liệu ảnh ra khỏi dữ liệu cửa hàng
        image_data = validated_data.pop('image', None)
        
        # Tạo cửa hàng trước
        store = Store.objects.create(**validated_data)
        
        # Nếu có gửi kèm ảnh thì tạo luôn StoreImage
        if image_data:
            from .models import StoreImage # Import ở đây để tránh lỗi vòng lặp
            
            # Lấy user đang đăng nhập (được truyền từ views)
            request = self.context.get('request')
            user = request.user if request else None

            # Lưu ảnh vào database
            StoreImage.objects.create(
                store=store,
                image=image_data,
                uploaded_by=user,
                state='private' # Hoặc 'public' tuỳ logic của bạn
            )
            
        return store

# 4. Approval Profile Serializer
class ApprovalProfileSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    approver_name = serializers.CharField(source='approver.username', read_only=True)
    submitter_name = serializers.ReadOnlyField(source='submitter.username')
    
    class Meta:
        model = ApprovalProfile
        fields = [
            'id', 
            'store', 
            'store_name', 
            'submitter', 
            'submitter_name', 
            'approver', 
            'approver_name', 
            'status', 
            'date_up', 
            'date_sign', 
            'note'
        ]
        read_only_fields = ['submitter', 'approver', 'status', 'date_up']