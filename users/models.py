from django.contrib.gis.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    phone = models.CharField(max_length=15, verbose_name="Phone Number")
    role = models.CharField(max_length=10, default='USER', verbose_name="Role")
    full_name = models.CharField(max_length=255, verbose_name="Full Name", blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name="Avatar")

    def __str__(self):
        return self.username

class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_histories', verbose_name="User")
    keyword = models.CharField(max_length=255, verbose_name="Keyword")                                                                                                                          
    search_location = models.PointField(null=True, blank=True, verbose_name="Location")
    create_at = models.DateField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Search History"
        verbose_name_plural = "Search Histories"
        ordering = ['-create_at']

    def __str__(self):
        return f"{self.user.username} searched '{self.keyword}'"