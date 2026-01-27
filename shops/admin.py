from django.contrib import admin
from django import forms
from django.utils.html import mark_safe
from leaflet.admin import LeafletGeoAdmin
from .models import Category, Store, StoreImage, ApprovalProfile

# 1. WIDGET & FORM
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'id')
    prepopulated_fields = {'slug': ('name',)}

class StoreAdminForm(forms.ModelForm):
    # --- Quick Upload Section (English) ---
    quick_image = forms.FileField(
        label="📸 Quick Upload (Multiple Images)",  # Đã sửa
        required=False,
        widget=MultipleFileInput(attrs={'multiple': True}), 
        help_text="Hold Ctrl to select multiple images. The FIRST image will be used to extract GPS data." # Đã sửa
    )
    batch_describe = forms.CharField(
        label="📝 Description for these images", # Đã sửa
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'E.g., Interior view, New menu...'}), # Đã sửa
        help_text="This description will be applied to all images you just selected." # Đã sửa
    )
    batch_state = forms.ChoiceField(
        label="Image Status", # Đã sửa
        choices=[('public', 'Public'), ('private', 'Private')],
        initial='public',
        required=False
    )
    class Meta:
        model = Store
        fields = '__all__'

# 2. INLINE (Store Images List)
class StoreImageInline(admin.TabularInline):
    model = StoreImage
    extra = 1
    fields = ('image', 'image_preview', 'describe', 'state', 'uploaded_by', 'time_up')
    readonly_fields = ('image_preview', 'time_up', 'uploaded_by')

    def image_preview(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" style="width: 80px; height:auto; border-radius: 5px;" />')
        return "No Image"
    image_preview.short_description = "Preview" # Đã sửa

# 3. STORE ADMIN
class StoreAdmin(LeafletGeoAdmin):
    form = StoreAdminForm
    
    list_display = ('name', 'category', 'address', 'rating_avg', 'state', 'count_images')
    list_filter = ('category', 'state')
    search_fields = ('name', 'address')
    readonly_fields = ('rating_avg', 'rating_count')
    
    settings_overrides = {
       'DEFAULT_CENTER': (10.0452, 105.7469),
       'DEFAULT_ZOOM': 13,
    }

    class Media:
        js = ('js/admin_auto_gps.js',)

    def count_images(self, obj):
        return obj.image.count()
    count_images.short_description = "Image Count" # Đã sửa

    # --- 1. SHOW/HIDE INLINE ---
    def get_inlines(self, request, obj=None):
        if obj:
            return [StoreImageInline] 
        return []

    # --- 2. SHOW/HIDE FIELDSETS ---
    def get_fieldsets(self, request, obj=None):
        # Basic fieldsets (English Headers)
        basic_fieldsets = [
            ('🏠 Store information', { # Đã sửa
                'fields': ('name', 'category', 'address', 'phone', 'email', 'describe', 'state', 'is_active', 'open_time', 'close_time')
            }),
            ('📍 Map location', { # Đã sửa
                'fields': ('location',)
            }),
            ('⭐ Ratings & Review', { # Đã sửa
                'fields': ('rating_avg', 'rating_count'),
                'classes': ('collapse',),
            }),
        ]

        if obj is None: 
            # Upload Section (English)
            upload_section = ('📤 QUICK UPLOAD & GPS EXTRACT', { # Đã sửa
                'fields': ('quick_image', 'batch_describe', 'batch_state'),
                'classes': ('wide', 'extrapretty'), 
                'description': 'Select images to automatically extract GPS coordinates and create an album.' # Đã sửa
            })
            return [upload_section] + basic_fieldsets
        else:
            return basic_fieldsets

    # --- SAVE MODEL ---
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        files = request.FILES.getlist('quick_image')
        batch_desc = form.cleaned_data.get('batch_describe')
        batch_state = form.cleaned_data.get('batch_state')
        
        if files:
            for f in files:
                StoreImage.objects.create(
                    store=obj,
                    image=f,
                    describe=batch_desc,       
                    state=batch_state,         
                    uploaded_by=request.user, 
                )
            self.message_user(request, f"✅ Successfully uploaded {len(files)} new images.") # Đã sửa

class ApprovalProfileAdmin(admin.ModelAdmin):
    list_display = ('store', 'submitter', 'status', 'date_up', 'approver')
    list_filter = ('status', 'date_up')
    search_fields = ('store__name', 'submitter__username')
    ordering = ('-date_up',)

admin.site.register(Category, CategoryAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(ApprovalProfile, ApprovalProfileAdmin)