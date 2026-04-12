from django.contrib import admin
from django import forms
from django.utils.html import mark_safe
from leaflet.admin import LeafletGeoAdmin
from .models import Category, Store, StoreImage, ApprovalProfile

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_preview', 'id')
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
    list_display = ('name', 'category', 'address', 'rating_avg', 'state_badge', 'count_images')
    list_filter = ('category', 'state')
    list_editable = ()  # state managed via change form
    search_fields = ('name', 'address')
    readonly_fields = ('rating_avg', 'rating_count')
    settings_overrides = {'DEFAULT_CENTER': (10.0452, 105.7469), 'DEFAULT_ZOOM': 13}

    class Media:
        js = ('js/admin_auto_gps.js', 'js/admin_bulk_delete.js')



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

class ApprovalNoteWidget(forms.Textarea):
    def __init__(self, store=None, *args, **kwargs):
        self.store = store
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        import json
        from django.utils.html import format_html, mark_safe
        from .models import StoreImage
        
        original_textarea = super().render(name, value, attrs, renderer)
        
        try:
            data = json.loads(value) if value else {}
        except json.JSONDecodeError:
            data = {}

        old_lat = self.store.location.y if self.store and self.store.location else 10.0452
        old_lng = self.store.location.x if self.store and self.store.location else 105.7469
        
        new_lat = data.get('latitude', old_lat)
        new_lng = data.get('longitude', old_lng)

        ui_html = f'''
        <div id="custom-note-editor" style="padding:15px; background:#fff; border:1px solid #ddd; margin-bottom:15px; border-radius:5px;">
            <h5 style="margin-top:0;">Chỉnh sửa dữ liệu JSON</h5>
            <div style="display:flex; flex-wrap:wrap; gap:10px;">
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Tên mới</label><input type="text" id="ne_name" value="{data.get('name', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Địa chỉ mới</label><input type="text" id="ne_address" value="{data.get('address', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Số điện thoại</label><input type="text" id="ne_phone" value="{data.get('phone', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Email</label><input type="text" id="ne_email" value="{data.get('email', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 100%;"><label style="font-weight:bold;display:block;">Mô tả mới</label><textarea id="ne_describe" style="width:100%; padding:5px;" onchange="updateNoteJson()">{data.get('describe', '')}</textarea></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Giờ mở cửa</label><input type="text" id="ne_open" value="{data.get('open_time', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Giờ đóng cửa</label><input type="text" id="ne_close" value="{data.get('close_time', '')}" style="width:100%; padding:5px;" onchange="updateNoteJson()"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Vĩ độ (Lat)</label><input type="number" step="any" id="ne_lat" value="{new_lat}" style="width:100%; padding:5px;" onchange="updateNoteJson(); updateMapPins();"></div>
                <div style="flex:1 1 45%;"><label style="font-weight:bold;display:block;">Kinh độ (Lng)</label><input type="number" step="any" id="ne_lng" value="{new_lng}" style="width:100%; padding:5px;" onchange="updateNoteJson(); updateMapPins();"></div>
            </div>
            
            <h4 style="margin-top:20px; font-weight:bold;">Bản đồ So sánh Vị trí</h4>
            <div id="note-map" style="width:100%; height:300px; border:1px solid #ccc; z-index:1; border-radius:5px;"></div>
            <p style="font-size:12px; color:#555; margin-top:5px;"><i>(Kéo thả marker Đỏ để chỉnh sửa tọa độ đề xuất)</i></p>
            
            <script>
            setTimeout(function() {{
                if (typeof L === 'undefined') return;
                var noteMap = L.map('note-map', {{ minZoom: 5, maxZoom: 20 }}).setView([{old_lat}, {old_lng}], 16);
                L.tileLayer('https://api.maptiler.com/maps/topo-v4/{{z}}/{{x}}/{{y}}@2x.png?key=8VtL7nDfk7i0W2TAHvlE', {{
                    maxZoom: 20,
                    crossOrigin: 'anonymous',
                    attribution: '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a>'
                }}).addTo(noteMap);
                
                var oldMarker = null;
                var newMarker = null;
                
                var oldLat = {old_lat};
                var oldLng = {old_lng};
                
                var originIcon = new L.Icon.Default();
                var redIcon = new L.Icon({{
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
                }});

                window.updateMapPins = function() {{
                    var nLat = parseFloat(document.getElementById('ne_lat').value);
                    var nLng = parseFloat(document.getElementById('ne_lng').value);
                    
                    if (oldMarker) noteMap.removeLayer(oldMarker);
                    if (newMarker) noteMap.removeLayer(newMarker);
                    
                    if (Math.abs(oldLat - nLat) < 0.00001 && Math.abs(oldLng - nLng) < 0.00001) {{
                        newMarker = L.marker([nLat, nLng], {{icon: redIcon, draggable: true}}).addTo(noteMap).bindPopup("Tọa độ trùng nhau");
                    }} else {{
                        oldMarker = L.marker([oldLat, oldLng], {{icon: originIcon}}).addTo(noteMap).bindPopup("Tọa độ cũ");
                        newMarker = L.marker([nLat, nLng], {{icon: redIcon, draggable: true}}).addTo(noteMap).bindPopup("Tọa độ đề xuất");
                    }}
                    
                    if (newMarker) {{
                        newMarker.on('dragend', function(e) {{
                            var pos = e.target.getLatLng();
                            document.getElementById('ne_lat').value = pos.lat;
                            document.getElementById('ne_lng').value = pos.lng;
                            updateNoteJson();
                        }});
                    }}
                }};
                
                window.updateNoteJson = function() {{
                    // attrs mapping issue handled by simple id mapping
                    var noteField = document.getElementById('id_note');
                    try {{
                        var data = JSON.parse(noteField.value || "{{}}");
                        data.name = document.getElementById('ne_name').value;
                        data.address = document.getElementById('ne_address').value;
                        data.phone = document.getElementById('ne_phone').value;
                        data.email = document.getElementById('ne_email').value;
                        data.describe = document.getElementById('ne_describe').value;
                        data.open_time = document.getElementById('ne_open').value;
                        data.close_time = document.getElementById('ne_close').value;
                        data.latitude = parseFloat(document.getElementById('ne_lat').value);
                        data.longitude = parseFloat(document.getElementById('ne_lng').value);
                        noteField.value = JSON.stringify(data);
                    }} catch (e) {{ console.log(e); }}
                }};
                
                updateMapPins();
            }}, 800);
            </script>
        '''

        new_images = data.get('new_images', [])
        if new_images:
            ui_html += '<div style="margin-top: 15px;"><strong>📸 Ảnh mới kèm theo:</strong><br><div style="display:flex; gap: 10px; margin-top: 10px;">'
            imgs = StoreImage.objects.filter(id__in=new_images)
            for img in imgs:
                if img.image:
                    ui_html += f'<a href="{img.image.url}" target="_blank"><img src="{img.image.url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 5px; border: 1px solid #ccc;" /></a>'
            ui_html += '</div></div>'
            
        deleted_images = data.get('deleted_images', [])
        if deleted_images:
            ui_html += '<div style="margin-top: 15px;"><strong>🗑️ Ảnh bị yêu cầu xóa:</strong><br><div style="display:flex; gap: 10px; margin-top: 10px; opacity: 0.6;">'
            imgs = StoreImage.objects.filter(id__in=deleted_images)
            for img in imgs:
                if img.image:
                    ui_html += f'<a href="{img.image.url}" target="_blank"><img src="{img.image.url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 5px; border: 2px solid #dc3545;" /></a>'
            ui_html += '</div></div>'

        ui_html += '</div>'
        
        return mark_safe(ui_html + f'<div style="display:none;">{original_textarea}</div>')

class ApprovalProfileAdminForm(forms.ModelForm):
    class Meta:
        model = ApprovalProfile
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        store = None
        if getattr(self, 'instance', None) and self.instance.pk:
            store = self.instance.store
        self.fields['note'].widget = ApprovalNoteWidget(store=store)

class ApprovalProfileAdmin(LeafletGeoAdmin):
    form = ApprovalProfileAdminForm
    list_display = ('store', 'submitter', 'status', 'date_up', 'approver', 'delete_button')
    list_filter = ('status', 'date_up')
    search_fields = ('store__name', 'submitter__username')
    ordering = ('-date_up',)

    class Media:
        js = (
            'js/admin_bulk_delete.js',
            'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
        )
        css = {
            'all': ('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',)
        }

    def delete_button(self, obj):
        return mark_safe(f'<a class="btn btn-danger btn-sm" href="/admin/shops/approvalprofile/{obj.pk}/delete/" title="Xóa"><i class="fas fa-trash"></i></a>')
    delete_button.short_description = 'Xóa'
    delete_button.allow_tags = True

admin.site.register(Category, CategoryAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(ApprovalProfile, ApprovalProfileAdmin)