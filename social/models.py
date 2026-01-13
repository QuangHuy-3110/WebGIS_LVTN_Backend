from django.db import models
from django.conf import settings

class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey('shops.Store', on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(default=5)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Gọi hàm save mặc định trước
        super().save(*args, **kwargs)
        # Sau khi lưu xong, cập nhật lại điểm trung bình cho Cửa hàng
        self.store.update_rating()

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey('shops.Store', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'store')