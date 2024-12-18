from rest_framework import serializers
from .models import CustomUser, UserKYC

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password')

    

    def create(self, validated_data):
        
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

# serializers.py
from rest_framework import serializers
from .models import UserKYC
import cv2
import numpy as np
import hashlib
import os
from django.core.files.uploadedfile import InMemoryUploadedFile
import io

from rest_framework import serializers
from .models import UserKYC
import cv2
import numpy as np
import hashlib
import os
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageEnhance
import io
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class UserKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserKYC
        fields = ['full_name', 'contact_number', 'address', 'country', 'selfie']

    def validate_selfie(self, value):
        try:
            # Read image file
            if isinstance(value, InMemoryUploadedFile):
                image_bytes = value.read()
                image = Image.open(io.BytesIO(image_bytes))
            else:
                raise serializers.ValidationError("Invalid image format")

            # Convert to RGB and resize the image
            image = image.convert("RGB")
            image = self._resize_image(image)

            # Save the image metadata to later use for duplicate detection
            image_metadata = self._process_image(image, value)

            # Compress and optimize the image
            optimized_image = self._compress_image(image)

            # Calculate image hash (SHA-256)
            image_hash = self._generate_image_hash(optimized_image)

            # Check for duplicate using the image hash
            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("This image has already been used. Please upload a different image.")

            # Store the image hash and metadata
            value.image_hash = image_hash
            value.metadata = image_metadata

            return self._save_image(optimized_image, value)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError(f"Error processing image: {str(e)}")

    def _resize_image(self, image):
        # Resize the image to ensure it's not too large
        max_size = (800, 800)  # Max size of 800x800 pixels
        image.thumbnail(max_size, Image.ANTIALIAS)
        return image

    def _process_image(self, image, value):
        # Perform quality enhancement (e.g., sharpen image)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)  # Double the sharpness
        image = self._convert_to_grayscale(image)

        # Image dimensions and compression check
        width, height = image.size
        if width < 200 or height < 200:
            raise serializers.ValidationError("Image resolution too low. Minimum 200x200 pixels required.")

        return {
            'width': width,
            'height': height,
            'format': value.content_type,
        }

    def _convert_to_grayscale(self, image):
        return image.convert("L")  # Convert to grayscale for easier processing

    def _compress_image(self, image):
        # Compress the image to reduce size (JPEG is efficient)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)  # Adjust quality to control compression level
        buffer.seek(0)
        return buffer

    def _generate_image_hash(self, optimized_image):
        # Use SHA-256 for better hash collision resistance
        image_hash = hashlib.sha256(optimized_image.read()).hexdigest()
        optimized_image.seek(0)  # Reset file pointer after reading
        return image_hash

    def _save_image(self, optimized_image, value):
        # Save the optimized image back to the uploaded file object
        value.seek(0)  # Reset file pointer
        value.write(optimized_image.read())
        value.seek(0)  # Reset file pointer again for saving
        return value

    def create(self, validated_data):
        image_hash = validated_data.get('selfie').image_hash

        # Check again for duplicates before saving
        if UserKYC.objects.filter(image_hash=image_hash).exists():
            raise serializers.ValidationError("This image has already been used. Please upload a different image.")

        # Create and save the UserKYC instance
        kyc = UserKYC.objects.create(**validated_data)
        kyc.image_hash = image_hash
        kyc.save()

        return kyc

    def update(self, instance, validated_data):
        if 'selfie' in validated_data:
            image_hash = validated_data['selfie'].image_hash
            # Check again for duplicates before updating
            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("This image has already been used. Please upload a different image.")
            
            # Update the hash if the image is new
            instance.image_hash = image_hash

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

