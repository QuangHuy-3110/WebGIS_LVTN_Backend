from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import Avg, Count
from django.contrib.gis.geos import Point
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@receiver(post_save, sender='shops.Store')
def broadcast_store_update(sender, instance, created, **kwargs):
    if instance.state == 'active':
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'store_updates',
            {
                'type': 'store_message',
                'message': {
                    'action': 'STORE_ADDED' if created else 'STORE_UPDATED',
                    'store_id': instance.id,
                    'name': instance.name,
                    'lat': instance.location.y if instance.location else None,
                    'lng': instance.location.x if instance.location else None
                }
            }
        )

class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    icon = models.ImageField(upload_to='categories/', null=True, blank=True, verbose_name="Category Icon")
    def __str__(self): return self.name

class Store(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='owned_stores')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    phone = models.CharField(max_length=15, verbose_name="Store Phone Number", null=True, blank=True)
    email = models.CharField(max_length=255, verbose_name="Store Email", null=True, blank=True)
    location = models.PointField(verbose_name='Coordinates')
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    state = models.CharField(max_length=50, verbose_name="Store Status", choices=STATUS_CHOICES, default='active')
    describe = models.TextField(blank=True)
    open_time = models.TimeField(verbose_name="Opening Time", null=True, blank=True)
    close_time = models.TimeField(verbose_name="Closing Time", null=True, blank=True)
    rating_avg = models.FloatField(default=0.0, verbose_name="Average Rating") 
    rating_count = models.IntegerField(default=0, verbose_name="Review Count")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    
    def __str__(self): return self.name
    
    def update_rating(self):
        stats = self.reviews.aggregate(average=Avg('rating'), count=Count('id'))
        self.rating_avg = stats['average'] or 0.0
        self.rating_count = stats['count'] or 0
        self.save() 

class StoreImage(models.Model):
    # --- QUAN TRỌNG: Thêm null=True, blank=True ---
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="image", null=True, blank=True)
    # ----------------------------------------------
    image = models.ImageField(upload_to='stores/', verbose_name="Image", null=True, blank=True)
    describe = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    state = models.CharField(max_length=50)
    time_up = models.TimeField(auto_now_add=True)
    
    def __str__(self): return f"Image {self.id}"

class ApprovalProfile(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='store')
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitter')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='approvals')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_up = models.DateTimeField(auto_now_add=True)
    date_sign = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

@receiver(post_save, sender=ApprovalProfile)
def auto_process_approval(sender, instance, created, **kwargs):
    if instance.status == 'approved':
        print(f"⚡ SIGNAL TRIGGERED: Processing profile #{instance.id}")
        try:
            from .models import StoreImage
            store = instance.store
            if isinstance(instance.note, str):
                try:
                    changes = json.loads(instance.note)
                except json.JSONDecodeError:
                    changes = {}
            else:
                changes = instance.note

            if changes.get('action') == 'CREATE_NEW':
                store.is_active = True
                store.state = 'active'
                StoreImage.objects.filter(store=store).update(state='public')
                print(f"🎉 New store activated: {store.name}")
            else:
                if 'new_images' in changes and isinstance(changes['new_images'], list):
                    StoreImage.objects.filter(id__in=changes['new_images']).update(state='public')
                if 'deleted_images' in changes and isinstance(changes['deleted_images'], list):
                    StoreImage.objects.filter(id__in=changes['deleted_images']).delete()
                print(f"✏️ Updating store info: {store.name}")

            fields_to_update = ['name', 'address', 'describe', 'phone', 'email', 'open_time', 'close_time', 'category']
            has_change = False
            for field in fields_to_update:
                if field in changes:
                    setattr(store, field, changes[field])
                    has_change = True

            if 'latitude' in changes and 'longitude' in changes:
                try:
                    lat = float(changes['latitude'])
                    lng = float(changes['longitude'])
                    store.location = Point(lng, lat)
                    has_change = True
                except ValueError: pass

            if has_change or changes.get('action') == 'CREATE_NEW':
                store.save()
        except Exception as e:
            print(f"❌ Error: {e}")