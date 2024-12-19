from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import uuid

class CustomUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, username, password, **extra_fields)

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    is_verified = models.BooleanField(default=False)
    is_kyc = models.BooleanField(default=False)
    is_submitted = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    rejection_times = models.IntegerField(default=0)
    unique_id = models.UUIDField(default=uuid.uuid4, editable=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

class UserKYC(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, default="none")
    contact_number = models.CharField(max_length=15)
    address = models.TextField()
    country = models.CharField(max_length=50)
    selfie = models.ImageField(upload_to="selfies/")
    face_hash = models.CharField(max_length=64, null=True, blank=True)
    image_hash = models.CharField(max_length=32, unique=True, null=True, blank=True)
    face_embeddings = models.JSONField(null=True, blank=True)
    s3_image_url = models.CharField(max_length=255, null=True, blank=True)  # Store S3 URL
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"KYC for {self.full_name} ({self.user.email})"

    class Meta:
        verbose_name = "User KYC"
        verbose_name_plural = "User KYCs"
        ordering = ['-created_at']
