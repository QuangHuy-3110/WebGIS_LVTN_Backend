from django.db import models
from django.conf import settings

class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey('shops.Store', on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(default=5, verbose_name="Rating")
    content = models.TextField(verbose_name="Content")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Call the default save method first
        super().save(*args, **kwargs)
        # After saving, update the average rating for the Store
        self.store.update_rating()

    def __str__(self):
        return f"Review by {self.user} for {self.store.name}"

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    store = models.ForeignKey('shops.Store', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'store')
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"

    def __str__(self):
        return f"{self.user} likes {self.store.name}"