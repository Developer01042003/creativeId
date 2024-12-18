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
    fullname = models.CharField(max_length=100,default="none")  # Added field for first name
     # Added field for last name
    contact_number = models.CharField(max_length=15)
    address = models.TextField()
    country = models.CharField(max_length=50)
    selfie = models.ImageField(upload_to="selfies/")
    image_hash = models.CharField(max_length=32, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"KYC for {self.first_name} {self.last_name} ({self.user.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "User KYC"
        verbose_name_plural = "User KYCs"
        ordering = ['-created_at']