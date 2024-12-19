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

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

class UserKYC(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected')
    ]

    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='kyc_profile'
    )
    full_name = models.CharField(max_length=255,default="one")
    contact_number = models.CharField(max_length=20)
    address = models.TextField()
    country = models.CharField(max_length=100)
    selfie = models.ImageField(
        upload_to='kyc_selfies/',
        null=True,
        blank=True
    )
    image_hash = models.CharField(
        max_length=64, 
        db_index=True,
        null=True,
        blank=True
    )
    face_id = models.CharField(
        max_length=255, 
        unique=True, 
        db_index=True,
        null=True,
        blank=True
    )
    face_confidence = models.FloatField(
        null=True,
        blank=True
    )
    s3_image_url = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )
    verification_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    rejection_reason = models.TextField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User KYC'
        verbose_name_plural = 'User KYCs'
        indexes = [
            models.Index(fields=['image_hash']),
            models.Index(fields=['face_id']),
            models.Index(fields=['verification_status']),
        ]

    def __str__(self):
        return f"KYC for {self.user.email}"

    def save(self, *args, **kwargs):
        # Update user status based on verification_status
        if self.verification_status == 'APPROVED':
            self.user.is_kyc = True
            self.user.is_rejected = False
        elif self.verification_status == 'REJECTED':
            self.user.is_kyc = False
            self.user.is_rejected = True
            self.user.rejection_times += 1
        
        self.user.is_submitted = True
        self.user.save()
        
        super().save(*args, **kwargs)

    @property
    def is_approved(self):
        return self.verification_status == 'APPROVED'

    @property
    def is_rejected(self):
        return self.verification_status == 'REJECTED'

    @property
    def is_pending(self):
        return self.verification_status == 'PENDING'

