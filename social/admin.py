from django.contrib import admin
from .models import Review, Favorite

class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'rating', 'created_at', 'short_content')
    list_filter = ('rating', 'created_at') # Lọc theo số sao và ngày tạo
    search_fields = ('user__username', 'store__name', 'content') # Tìm theo tên user, tên quán, nội dung
    readonly_fields = ('created_at',)

    # Hàm hiển thị nội dung ngắn gọn để bảng không bị vỡ nếu review quá dài
    def short_content(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    short_content.short_description = "Nội dung"

    class Media:
        js = ('js/admin_bulk_delete.js',)

class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'store')
    search_fields = ('user__username', 'store__name')
    list_filter = ('store',)

    class Media:
        js = ('js/admin_bulk_delete.js',)

admin.site.register(Review, ReviewAdmin)
admin.site.register(Favorite, FavoriteAdmin)