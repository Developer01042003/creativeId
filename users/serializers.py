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

class UserKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserKYC
        fields = ['full_name','contact_number', 'address', 'country', 'selfie']

    def validate_selfie(self, value):
        try:
            # Read image file
            if isinstance(value, InMemoryUploadedFile):
                image_bytes = value.read()
                # Convert to numpy array
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                raise serializers.ValidationError("Invalid image format")

            if img is None:
                raise serializers.ValidationError("Unable to process image")

            # 1. Check image dimensions
            height, width = img.shape[:2]
            if width < 200 or height < 200:
                raise serializers.ValidationError("Image resolution too low. Minimum 200x200 pixels required.")

            # 2. Face Detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            if len(faces) == 0:
                raise serializers.ValidationError("No face detected in the image")
            if len(faces) > 1:
                raise serializers.ValidationError("Multiple faces detected. Please submit a selfie with only your face")

            # 3. Blur Detection
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var < 100:  # Threshold for blur detection
                raise serializers.ValidationError("Image is too blurry")

            # 4. Brightness Check
            average_brightness = np.mean(gray)
            if average_brightness < 40:  # Too dark
                raise serializers.ValidationError("Image is too dark")
            if average_brightness > 240:  # Too bright
                raise serializers.ValidationError("Image is too bright")

            # 5. Image Size Check
            if value.size > 5 * 1024 * 1024:  # 5MB limit
                raise serializers.ValidationError("Image size too large. Maximum 5MB allowed.")

            # 6. Duplicate Check using MD5 hash
            value.seek(0)  # Reset file pointer
            image_hash = hashlib.md5(value.read()).hexdigest()
            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("This image has already been used")

            # Store hash for saving
            value.image_hash = image_hash

            # Reset file pointer for saving
            value.seek(0)
            return value

        except Exception as e:
            raise serializers.ValidationError(f"Error processing image: {str(e)}")

    def create(self, validated_data):
        # Store the hash if it exists
        image_hash = getattr(validated_data['selfie'], 'image_hash', None)
        kyc = UserKYC.objects.create(**validated_data)
        if image_hash:
            kyc.image_hash = image_hash
            kyc.save()
        return kyc

    def update(self, instance, validated_data):
        if 'selfie' in validated_data:
            # Store the hash if it exists
            image_hash = getattr(validated_data['selfie'], 'image_hash', None)
            if image_hash:
                instance.image_hash = image_hash
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
