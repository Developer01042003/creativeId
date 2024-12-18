from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, UserKYC

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'is_verified', 'is_staff', 'is_superuser')
    list_filter = ('is_verified', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email')
    ordering = ('username',)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_verified'),
        }),
    )

from django.utils.html import format_html

@admin.register(UserKYC)
class UserKYCAdmin(admin.ModelAdmin):
    list_display = ('contact_number', 'country', 'display_selfie', 'image_hash')
    search_fields = ('contact_number', 'country', 'image_hash')
    list_filter = ('country',)
    readonly_fields = ('image_hash',)

    def display_selfie(self, obj):
        if obj.selfie:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover;" />', obj.selfie.url)
        return "No Selfie"
    display_selfie.short_description = "Selfie Preview"


# Register the CustomUser model with the custom admin
admin.site.register(CustomUser, CustomUserAdmin)
