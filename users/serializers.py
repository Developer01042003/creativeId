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

import hashlib
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from rest_framework import serializers
from .models import UserKYC
import io
from django.core.files.uploadedfile import InMemoryUploadedFile
import logging

logger = logging.getLogger(__name__)

class UserKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserKYC
        fields = ['full_name', 'contact_number', 'address', 'country', 'selfie']

    def validate_selfie(self, value):
        try:
            # Step 1: Read and process the image
            if isinstance(value, InMemoryUploadedFile):
                image_bytes = value.read()
                image = Image.open(io.BytesIO(image_bytes))
            else:
                raise serializers.ValidationError("Invalid image format")
            
            img = np.array(image)
            if img is None:
                raise serializers.ValidationError("Unable to process image")

            # Step 2: Perform all validations on the image
            # Resolution check
            height, width = img.shape[:2]
            if width < 200 or height < 200:
                raise serializers.ValidationError("Image resolution too low. Minimum 200x200 pixels required.")

            # Face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) == 0:
                raise serializers.ValidationError("No face detected in the image")
            if len(faces) > 1:
                raise serializers.ValidationError("Multiple faces detected. Please submit a selfie with only your face")

            # Blur detection
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var < 100:  # Threshold for blur detection
                raise serializers.ValidationError("Image is too blurry")

            # Brightness check
            average_brightness = np.mean(gray)
            if average_brightness < 40:  # Too dark
                raise serializers.ValidationError("Image is too dark")
            if average_brightness > 240:  # Too bright
                raise serializers.ValidationError("Image is too bright")

            # Fake image check
            if self.is_mirror_or_fake(img):
                raise serializers.ValidationError("The image appears to be a screen capture or mirror image. Please submit a genuine selfie.")

            # Step 3: Process and compress the image before saving
            optimized_image = self._compress_image(image)

            # Step 4: Generate the image hash
            image_hash = self._generate_image_hash(optimized_image)

            # Step 5: Check for duplicate image hash in the database
            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("This image has already been used. Please upload a different image.")

            # Step 6: Save image hash and metadata
            image_metadata = self._process_image(image, value)
            value.image_hash = image_hash
            value.metadata = image_metadata

            # Step 7: Save the processed image
            return self._save_image(optimized_image, value)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError(f"Error processing image: {str(e)}")

    def is_mirror_or_fake(self, img):
        # Check if the image has reflective artifacts or unusual pixel patterns that suggest a screen capture
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)

        # Detect horizontal or vertical lines which might suggest a reflection or screen capture
        horizontal_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=200, maxLineGap=20)
        vertical_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=200, maxLineGap=20)

        if horizontal_lines is not None or vertical_lines is not None:
            return True  # Likely to be a screen capture or fake image

        return False

    def _process_image(self, image, value):
        # Perform image quality enhancement, e.g., sharpening
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)  # Double the sharpness

        # Check image dimensions and compression
        width, height = image.size
        if width < 200 or height < 200:
            raise serializers.ValidationError("Image resolution too low. Minimum 200x200 pixels required.")

        return {
            'width': width,
            'height': height,
            'format': value.content_type,
        }

    def _compress_image(self, image):
        # Compress image to reduce size
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)  # Adjust quality to control compression level
        buffer.seek(0)
        return buffer

    def _generate_image_hash(self, optimized_image):
        # Generate SHA-256 hash of the image for duplication check
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

        # Check for duplicates before saving
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
