from django.contrib import admin
from django import forms
from django.utils.html import mark_safe
from leaflet.admin import LeafletGeoAdmin
from .models import Category, Store, StoreImage, ApprovalProfile

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_preview', 'id', 'delete_button')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)
    readonly_fields = ('icon_preview',)

    class Media:
        js = ('js/admin_bulk_delete.js',)

    def icon_preview(self, obj):
        if obj.icon:
            return mark_safe(f'<a href="{obj.icon.url}" class="admin-image-modal"><img src="{obj.icon.url}" style="width: 30px; height: 30px; object-fit: contain;" /></a>')
        return "-"
    icon_preview.short_description = "Icon"

    def delete_button(self, obj):
        return mark_safe(f'<a class="btn btn-danger btn-sm" href="/admin/shops/category/{obj.pk}/delete/" title="Xóa"><i class="fas fa-trash"></i></a>')
    delete_button.short_description = 'Xóa'
    delete_button.allow_tags = True

class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            clean_data = []
            for item in data:
                out = super().clean(item, initial)
                if out:
                    clean_data.append(out)
            return clean_data
        return super().clean(data, initial)

class StoreAdminForm(forms.ModelForm):
    # Hidden field to store uploaded image IDs from JS
    uploaded_image_ids = forms.CharField(widget=forms.HiddenInput(), required=False)

    quick_image = MultipleFileField(
        label="📸 Quick Upload & Auto GPS",
        required=False,
        widget=MultipleFileInput(attrs={'multiple': True}),
        help_text="Select images to extract GPS coordinates. Images will be uploaded immediately."
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

    # --- Store field overrides ---
    state = forms.ChoiceField(
        label="Store Status",
        choices=[('active', '✅ Active'), ('inactive', '🔴 Inactive')],
        initial='active',
        required=True,
        help_text="Select the operational status of the store."
    )
    email = forms.EmailField(
        label="Email",
        required=False,
        help_text="Optional."
    )
    open_time = forms.TimeField(
        label="Opening Time",
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
        help_text="Optional."
    )
    close_time = forms.TimeField(
        label="Closing Time",
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
        help_text="Optional."
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
            return mark_safe(f'<a href="{obj.image.url}" class="admin-image-modal"><img src="{obj.image.url}" style="width: 80px; height:auto; border-radius: 5px;" /></a>')
        return "No Image"

class StoreAdmin(LeafletGeoAdmin):
    form = StoreAdminForm
    list_display = ('name', 'category', 'address', 'rating_avg', 'state_badge', 'count_images', 'delete_button')
    list_filter = ('category', 'state')
    list_editable = ()  # state managed via change form
    search_fields = ('name', 'address')
    readonly_fields = ('rating_avg', 'rating_count')
    settings_overrides = {'DEFAULT_CENTER': (10.0452, 105.7469), 'DEFAULT_ZOOM': 13}

    class Media:
        js = ('js/admin_auto_gps.js', 'js/admin_bulk_delete.js')

    def delete_button(self, obj):
        return mark_safe(f'<a class="btn btn-danger btn-sm" href="/admin/shops/store/{obj.pk}/delete/" title="Xóa"><i class="fas fa-trash"></i></a>')
    delete_button.short_description = 'Xóa'
    delete_button.allow_tags = True

    def state_badge(self, obj):
        if obj.state == 'active':
            return mark_safe('<span style="background:#28a745;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">✅ Active</span>')
        return mark_safe('<span style="background:#dc3545;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">🔴 Inactive</span>')
    state_badge.short_description = 'Status'
    state_badge.allow_tags = True

    def count_images(self, obj):
        return obj.image.count()
    count_images.short_description = 'Images'

    def get_inlines(self, request, obj=None):
        return [StoreImageInline] if obj else []

    def get_fieldsets(self, request, obj=None):
        basic_fieldsets = [
            ('🏠 Store Information', {'fields': ('name', 'category', 'address', 'phone', 'email', 'describe', 'state', 'is_active', 'open_time', 'close_time')}),
            ('📍 Map Location', {'fields': ('location',)}),
            ('⭐ Ratings', {'fields': ('rating_avg', 'rating_count'), 'classes': ('collapse',)}),
        ]
        if obj is None:
            upload_section = ('📤 QUICK UPLOAD', {
                # uploaded_image_ids must be here so JS can find the input and fill in the IDs
                'fields': ('quick_image', 'batch_describe', 'batch_state', 'uploaded_image_ids'),
                'classes': ('wide', 'extrapretty'),
            })
            return [upload_section] + basic_fieldsets
        return basic_fieldsets

    @admin.action(description="🗑️ Xóa các cửa hàng đã chọn (Kèm xóa file vật lý)")
    def delete_selected_stores_with_images(self, request, queryset):
        deleted_count = 0
        for store in queryset:
            # Xóa các file ảnh vật lý khỏi ổ cứng
            for img_obj in store.image.all():
                if img_obj.image:
                    img_obj.image.delete(save=False)
            # Xóa cửa hàng (các ràng buộc model sẽ tự động CASCADE)
            store.delete()
            deleted_count += 1
        self.message_user(request, f"✅ Đã xóa thành công {deleted_count} cửa hàng và toàn bộ ảnh vật lý đi kèm.")

    actions = [delete_selected_stores_with_images]

    def save_model(self, request, obj, form, change):
        # 1. Save the Store first to get its ID
        super().save_model(request, obj, form, change)

        print(f"DEBUG: Saved Store '{obj.name}' (ID: {obj.id})")

        # 2. Luồng mới: Link trực tiếp từ files được post lên (tránh rác dữ liệu)
        files = request.FILES.getlist('quick_image')
        if files:
            batch_desc = form.cleaned_data.get('batch_describe')
            batch_state = form.cleaned_data.get('batch_state')
            count = 0
            for f in files:
                StoreImage.objects.create(
                    store=obj,
                    image=f,
                    describe=batch_desc,
                    state=batch_state,
                    uploaded_by=request.user
                )
                count += 1
            print(f"DEBUG: Successfully uploaded and linked {count} new images.")

        # 3. Luồng cũ: Link uploaded images IDs (giữ lại cho tương thích ngược nếu cần)
        image_ids_str = form.cleaned_data.get('uploaded_image_ids')
        if image_ids_str:
            try:
                img_ids = [int(id) for id in image_ids_str.split(',') if id.strip().isdigit()]
                if img_ids:
                    batch_desc = form.cleaned_data.get('batch_describe')
                    batch_state = form.cleaned_data.get('batch_state')
                    updated_count = StoreImage.objects.filter(id__in=img_ids).update(
                        store=obj,
                        describe=batch_desc,
                        state=batch_state
                    )
            except Exception as e:
                print(f"ERROR: Failed to link images: {e}")

class ApprovalProfileAdmin(admin.ModelAdmin):
    list_display = ('store', 'submitter', 'status', 'date_up', 'approver', 'delete_button')
    list_filter = ('status', 'date_up')
    search_fields = ('store__name', 'submitter__username')
    ordering = ('-date_up',)

    class Media:
        js = ('js/admin_bulk_delete.js',)

    def delete_button(self, obj):
        return mark_safe(f'<a class="btn btn-danger btn-sm" href="/admin/shops/approvalprofile/{obj.pk}/delete/" title="Xóa"><i class="fas fa-trash"></i></a>')
    delete_button.short_description = 'Xóa'
    delete_button.allow_tags = True

admin.site.register(Category, CategoryAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(ApprovalProfile, ApprovalProfileAdmin)