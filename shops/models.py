from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import Avg, Count
from django.contrib.gis.geos import Point
from django.db.models.signals import post_save
from django.dispatch import receiver
import json

class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Store(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='owned_stores')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    phone = models.CharField(max_length=15, verbose_name="Store Phone Number", null=True, blank=True)
    email = models.CharField(max_length=255, verbose_name="Store Email")
    location = models.PointField(verbose_name='Coordinates')
    state = models.CharField(max_length=50, verbose_name="Store Status")
    describe = models.TextField(blank=True)
    open_time = models.TimeField(verbose_name="Opening Time")
    close_time = models.TimeField(verbose_name="Closing Time")
    rating_avg = models.FloatField(default=0.0, verbose_name="Average Rating") 
    rating_count = models.IntegerField(default=0, verbose_name="Review Count")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")

    def __str__(self):
        return self.name

    def update_rating(self):
        stats = self.reviews.aggregate(average=Avg('rating'), count=Count('id'))
        
        self.rating_avg = stats['average'] or 0.0 # Default to 0 if no reviews
        self.rating_count = stats['count'] or 0
        self.save() 

class StoreImage(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="image")
    image = models.ImageField(upload_to='stores/', verbose_name="Image", null=True, blank=True)
    describe = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    state = models.CharField(max_length=50)
    time_up = models.TimeField(auto_now_add=True)

    # Nếu bạn muốn thêm các trường GPS capture như đã thảo luận trước đó, hãy uncomment đoạn dưới:
    # lat_capture = models.FloatField(null=True, blank=True, verbose_name="Captured Latitude")
    # lng_capture = models.FloatField(null=True, blank=True, verbose_name="Captured Longitude")
    # address_capture = models.CharField(max_length=500, null=True, blank=True, verbose_name="Captured Address")

    def __str__(self):
        return f"Image for {self.store.name}"

class ApprovalProfile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='store')
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitter')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='approvals')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_up = models.DateTimeField(auto_now_add=True)
    date_sign = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

# --- SIGNAL AUTO-PROCESSING ---

@receiver(post_save, sender=ApprovalProfile)
def auto_process_approval(sender, instance, created, **kwargs):
    """
    This function runs automatically whenever an ApprovalProfile is APPROVED.
    """
    if instance.status == 'approved':
        print(f"⚡ SIGNAL TRIGGERED: Processing profile #{instance.id}")
        try:
            # 1. Necessary Import to avoid circular import errors
            from .models import StoreImage
            
            # 2. Initialize variables
            store = instance.store
            if isinstance(instance.note, str):
                try:
                    changes = json.loads(instance.note)
                except json.JSONDecodeError:
                    changes = {}
            else:
                changes = instance.note

            # --- CASE A: APPROVING A NEW STORE CREATION REQUEST ---
            if changes.get('action') == 'CREATE_NEW':
                # 1. Activate the store
                store.is_active = True
                store.state = 'active'
                
                # 2. Make ALL images of this store Public
                StoreImage.objects.filter(store=store).update(state='public')
                
                print(f"🎉 [Signal] New store activated & Images public: {store.name}")

            # --- CASE B: APPROVING A MODIFICATION REQUEST ---
            else:
                # 1. Handle Images (Specific images only)
                if 'new_images' in changes and isinstance(changes['new_images'], list):
                    StoreImage.objects.filter(id__in=changes['new_images']).update(state='public')
                    print(f"✅ [Signal] Published {len(changes['new_images'])} new images.")

                if 'deleted_images' in changes and isinstance(changes['deleted_images'], list):
                    StoreImage.objects.filter(id__in=changes['deleted_images']).delete()
                    print(f"🗑️ [Signal] Deleted {len(changes['deleted_images'])} old images.")

                print(f"✏️ [Signal] Updating store info: {store.name}")

            # --- COMMON PART: UPDATE TEXT INFO & LOCATION ---
            # (Applies to both Create and Update to ensure latest data)
            
            # 1. Update basic information fields
            fields_to_update = ['name', 'address', 'describe', 'phone', 'email', 'open_time', 'close_time', 'category']
            has_change = False
            
            for field in fields_to_update:
                if field in changes: # Only update if data was sent
                    setattr(store, field, changes[field])
                    has_change = True

            # 2. Update Coordinates (if any)
            if 'latitude' in changes and 'longitude' in changes:
                try:
                    lat = float(changes['latitude'])
                    lng = float(changes['longitude'])
                    store.location = Point(lng, lat) # GeoDjango: (Longitude, Latitude)
                    has_change = True
                    print(f"📍 [Signal] Coordinates updated: {lat}, {lng}")
                except ValueError:
                    print("❌ [Signal] Invalid coordinate format")

            # 3. Save Store if there were changes
            if has_change or changes.get('action') == 'CREATE_NEW':
                store.save()
                print("✅ [Signal] Store saved successfully.")

        except Exception as e:
            print(f"❌ [Signal] Error processing approval: {e}")