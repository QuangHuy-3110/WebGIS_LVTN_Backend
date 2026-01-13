from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import Avg, Count

class Category (models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Store (models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='owned_stores')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    phone = models.CharField(max_length=15, verbose_name="So dien thoai cua hang", null=True, blank=True)
    email = models.CharField(max_length=255, verbose_name="Email cua hang")
    location = models.PointField(verbose_name='Toa do')
    state = models.CharField(max_length=50, verbose_name="Trang thai cua hang")
    describe = models.TextField(blank=True)
    open_time = models.TimeField(verbose_name="Gio mo cua")
    close_time = models.TimeField(verbose_name="Gio dong cua")
    rating_avg = models.FloatField(default=0.0, verbose_name="Diem danh gia trung binh") # Tương ứng sosaoCH
    rating_count = models.IntegerField(default=0, verbose_name="So luot danh gia")

    def __str__(self):
        return self.name

    def update_rating(self):
        stats = self.reviews.aggregate(average=Avg('rating'), count=Count('id'))
        
        self.rating_avg = stats['average'] or 0.0 # Nếu chưa có review nào thì là 0
        self.rating_count = stats['count'] or 0
        self.save() 

class StoreImage (models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="image")
    image = models.ImageField(upload_to='stores/', verbose_name="Hinh anh", null=True, blank=True)
    describe = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    state = models.CharField(max_length=50)
    time_up = models.TimeField(verbose_name='Thoi gian chup')

    def __str__(self):
        return f"Image for {self.store.name}"

class ApprovalProfile (models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='store')
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitter')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='approvals')
    status = models.CharField(max_length=20)
    date_up = models.DateTimeField(auto_now_add=True)
    date_sign = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)