# from django.db import models
from django.contrib.gis.db import models
from django.contrib.auth.models import AbstractUser

class User (AbstractUser):
    phone = models.CharField (max_length=15, verbose_name="So dien thoai")
    role = models.CharField (max_length= 10, default='USER', verbose_name="Vai tro")
    full_name = models.CharField(max_length=255, verbose_name="Ho va ten", blank=True)
    avatar = models.ImageField (upload_to='avatars/', null=True, blank=True)

    def __str__(self):
        return self.username
    
class SearchHistory (models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_histories')
    keyword = models.CharField(max_length=255)                                                                                                                          
    search_location = models.PointField(null=True, blank=True)
    create_at = models.DateField(auto_now_add=True)