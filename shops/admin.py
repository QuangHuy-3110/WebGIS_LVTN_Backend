from django.contrib import admin
from django import forms
from django.utils.html import mark_safe
from leaflet.admin import LeafletGeoAdmin
from .models import Category, Store, StoreImage, ApprovalProfile

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_preview', 'id') # Thêm icon_preview
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

    def icon_preview(self, obj):
        if obj.icon:
            return mark_safe(f'<img src="{obj.icon.url}" style="width: 30px; height: 30px; object-fit: contain;" />')
        return "-"
    icon_preview.short_description = "Icon"

class StoreAdminForm(forms.ModelForm):
    # Ô ẩn để chứa ID ảnh từ JS gửi lên
    uploaded_image_ids = forms.CharField(widget=forms.HiddenInput(), required=False)

    quick_image = forms.FileField(
        label="📸 Quick Upload & Auto GPS",
        required=False,
        widget=MultipleFileInput(attrs={'multiple': True}), 
        help_text="Chọn ảnh để lấy tọa độ. Ảnh sẽ được upload ngay lập tức."
    )
    batch_describe = forms.CharField(
        label="📝 Description for these images",
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    batch_state = forms.ChoiceField(
        label="Image Status",
        choices=[('public', 'Public'), ('private', 'Private')],
        initial='public',
        required=False
    )
    class Meta:
        model = Store
        fields = '__all__'

class StoreImageInline(admin.TabularInline):
    model = StoreImage
    extra = 1
    fields = ('image', 'image_preview', 'describe', 'state', 'uploaded_by')
    readonly_fields = ('image_preview', 'uploaded_by')
    def image_preview(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" style="width: 80px; height:auto; border-radius: 5px;" />')
        return "No Image"

class StoreAdmin(LeafletGeoAdmin):
    form = StoreAdminForm
    list_display = ('name', 'category', 'address', 'rating_avg', 'state', 'count_images')
    list_filter = ('category', 'state')
    search_fields = ('name', 'address')
    readonly_fields = ('rating_avg', 'rating_count')
    settings_overrides = {'DEFAULT_CENTER': (10.0452, 105.7469), 'DEFAULT_ZOOM': 13}

    class Media:
        js = ('js/admin_auto_gps.js',)

    def count_images(self, obj):
        return obj.image.count()

    def get_inlines(self, request, obj=None):
        return [StoreImageInline] if obj else []

    def get_fieldsets(self, request, obj=None):
        basic_fieldsets = [
            ('🏠 Store information', {'fields': ('name', 'category', 'address', 'phone', 'email', 'describe', 'state', 'is_active', 'open_time', 'close_time')}),
            ('📍 Map location', {'fields': ('location',)}),
            ('⭐ Ratings', {'fields': ('rating_avg', 'rating_count'), 'classes': ('collapse',)}),
        ]
        if obj is None: 
            upload_section = ('📤 QUICK UPLOAD', {
                # uploaded_image_ids phải có mặt ở đây thì JS mới tìm thấy input để điền ID vào
                'fields': ('quick_image', 'batch_describe', 'batch_state', 'uploaded_image_ids'), 
                'classes': ('wide', 'extrapretty'), 
            })
            return [upload_section] + basic_fieldsets
        return basic_fieldsets

    def save_model(self, request, obj, form, change):
        # 1. Lưu Cửa hàng trước để có ID (obj.id)
        super().save_model(request, obj, form, change)
        
        print(f"DEBUG: Đã lưu Store '{obj.name}' (ID: {obj.id})")

        # 2. Xử lý liên kết ảnh
        image_ids_str = form.cleaned_data.get('uploaded_image_ids')
        print(f"DEBUG: Danh sách ID ảnh nhận được: '{image_ids_str}'")

        if image_ids_str:
            try:
                # Chuyển chuỗi "15,16,17" -> list [15, 16, 17]
                img_ids = [int(id) for id in image_ids_str.split(',') if id.strip().isdigit()]
                
                if img_ids:
                    batch_desc = form.cleaned_data.get('batch_describe')
                    batch_state = form.cleaned_data.get('batch_state')

                    # Cập nhật Store cho các ảnh đó
                    updated_count = StoreImage.objects.filter(id__in=img_ids).update(
                        store=obj,
                        describe=batch_desc,
                        state=batch_state
                    )
                    print(f"DEBUG: Đã cập nhật thành công {updated_count} ảnh.")
                    self.message_user(request, f"✅ Đã liên kết {updated_count} ảnh vào cửa hàng.")
                else:
                    print("DEBUG: Không có ID hợp lệ nào để cập nhật.")
            except Exception as e:
                print(f"ERROR: Lỗi khi liên kết ảnh: {e}")
        else:
            print("DEBUG: Không nhận được uploaded_image_ids nào.")

class ApprovalProfileAdmin(admin.ModelAdmin):
    list_display = ('store', 'submitter', 'status', 'date_up', 'approver')
    list_filter = ('status', 'date_up')
    search_fields = ('store__name', 'submitter__username')
    ordering = ('-date_up',)

admin.site.register(Category, CategoryAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(ApprovalProfile, ApprovalProfileAdmin)