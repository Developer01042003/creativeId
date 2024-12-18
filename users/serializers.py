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
import imagehash

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
            face = self.detect_face(img)
            if face is None:
                raise serializers.ValidationError("No face detected in the image")

            # Crop face from the image
            cropped_face = self.crop_face(img, face)

            # Generate hash for the cropped face
            cropped_face_hash = self.generate_face_hash(cropped_face)

            # Check for duplicate face hash
            if self.is_duplicate(cropped_face_hash):
                raise serializers.ValidationError("This face image has already been used. Please upload a different image.")

            # Perform other checks (blurry, brightness, fake detection)
            if self.is_blurry(img):
                raise serializers.ValidationError("Image is too blurry")

            if not self.check_brightness(img):
                raise serializers.ValidationError("Image brightness is either too low or too high")

            if self.is_mirror_or_fake(img):
                raise serializers.ValidationError("The image appears to be a screen capture or mirror image. Please submit a genuine selfie.")

            # Compress and save the image
            optimized_image = self._compress_image(image)
            image_hash = self._generate_image_hash(optimized_image)

            # Store image hash and metadata
            value.image_hash = cropped_face_hash  # Save only the cropped face hash
            value.metadata = self._process_image(image, value)

            # Save the processed image
            return self._save_image(optimized_image, value)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError(f"Error processing image: {str(e)}")

    def detect_face(self, img):
        # Use OpenCV's CascadeClassifier for face detection
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) == 0:
            return None  # No face detected
        if len(faces) > 1:
            raise serializers.ValidationError("Multiple faces detected. Please submit a selfie with only your face")

        return faces[0]  # Return the first face

    def crop_face(self, img, face):
        # Crop the face from the image using the bounding box
        x, y, w, h = face
        return img[y:y+h, x:x+w]

    def generate_face_hash(self, cropped_face):
        # Convert cropped face to Image format
        face_image = Image.fromarray(cropped_face)
        face_hash = imagehash.phash(face_image)  # Perceptual hash for better similarity matching
        return str(face_hash)

    def is_duplicate(self, face_hash):
        # Check for duplicates based on cropped face hash
        existing_hashes = UserKYC.objects.values_list('face_hash', flat=True)
        for existing_hash in existing_hashes:
            if abs(int(face_hash, 16) - int(existing_hash, 16)) < 5:  # Threshold for similarity (80% match)
                return True
        return False

    def is_blurry(self, img):
        # Blur detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return laplacian_var < 100  # Threshold for blur detection

    def check_brightness(self, img):
        # Brightness check
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        average_brightness = np.mean(gray)
        return 40 <= average_brightness <= 240  # Acceptable brightness range

    def is_mirror_or_fake(self, img):
        # Check for screen captures or mirror-like reflections
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        
        # Detect horizontal or vertical lines that may suggest a screen capture
        horizontal_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=200, maxLineGap=20)
        vertical_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=200, maxLineGap=20)
        
        return horizontal_lines is not None or vertical_lines is not None

    def _process_image(self, image, value):
        # Enhance image quality (optional)
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
        image.save(buffer, format="JPEG", quality=85)  # Adjust quality for compression
        buffer.seek(0)
        return buffer

    def _generate_image_hash(self, optimized_image):
        # Generate SHA-256 hash for the full image (for database storage)
        image_hash = hashlib.sha256(optimized_image.read()).hexdigest()
        optimized_image.seek(0)  # Reset file pointer
        return image_hash

    def _save_image(self, optimized_image, value):
        # Save the optimized image back to the uploaded file object
        value.seek(0)  # Reset file pointer
        value.write(optimized_image.read())
        value.seek(0)  # Reset file pointer again for saving
        return value

    def create(self, validated_data):
        # Check for duplicates before saving
        image_hash = validated_data.get('selfie').image_hash
        if UserKYC.objects.filter(image_hash=image_hash).exists():
            raise serializers.ValidationError("This image has already been used. Please upload a different image.")

        # Create and save the UserKYC instance
        kyc = UserKYC.objects.create(**validated_data)
        kyc.image_hash = image_hash
        kyc.save()

        return kyc

    def update(self, instance, validated_data):
        # If there's a new selfie, check for duplicates again
        if 'selfie' in validated_data:
            image_hash = validated_data['selfie'].image_hash
            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("This image has already been used. Please upload a different image.")
            
            # Update the hash if the image is new
            instance.image_hash = image_hash

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

