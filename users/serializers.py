from rest_framework import serializers
from .models import CustomUser, UserKYC

import boto3
import os

s3_client = boto3.client(
    's3',
    region_name='us-east-1',
    aws_access_key_id='AKIAUZPNLWACTQ4UERLU',
    aws_secret_access_key='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'
)

rekognition_client = boto3.client(
    'rekognition',
    region_name='us-east-1',
    aws_access_key_id='AKIAUZPNLWACTQ4UERLU',
    aws_secret_access_key='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'
)

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
import io
import logging
import boto3
from PIL import Image
from rest_framework import serializers
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import UserKYC

logger = logging.getLogger(__name__)

# Initialize the Rekognition and S3 clients


# Define your S3 bucket name
S3_BUCKET_NAME = 'imagingkyc'

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

            # Step 2: Perform all validations on the image
            # Resolution check
            width, height = image.size
            if width < 200 or height < 200:
                raise serializers.ValidationError("Sorry, cannot proceed: Image resolution too low. Minimum 200x200 pixels required.")

            # Check for open eyes and duplicate face using Rekognition
            if not self.is_eyes_open(image_bytes):
                raise serializers.ValidationError("Sorry, cannot proceed: Eyes must be open in the selfie.")

            if self.is_duplicate_face(image_bytes):
                raise serializers.ValidationError("Sorry, cannot proceed: This face image has already been used. Please upload a different image.")

            # Compress and save the image
            optimized_image = self._compress_image(image)
            image_hash = self._generate_image_hash(optimized_image)
            value.image_hash = image_hash

            # Save the processed image
            return self._save_image(optimized_image, value)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError(f"Sorry, cannot proceed: Error processing image.")

    def is_eyes_open(self, image_bytes):
        # Analyze the image for facial features
        response = rekognition_client.detect_faces(
            Image={'Bytes': image_bytes},
            Attributes=['ALL']
        )
        if not response['FaceDetails']:
            return False

        face_details = response['FaceDetails'][0]
        left_eye_open = face_details['EyesOpen']['Value']
        right_eye_open = face_details['EyesOpen']['Value']

        return left_eye_open and right_eye_open

    def is_duplicate_face(self, image_bytes):
        # Retrieve all reference images from S3 and compare
        for user_kyc in UserKYC.objects.all():
            if user_kyc.s3_image_url:
                response = rekognition_client.compare_faces(
                    SourceImage={'Bytes': image_bytes},
                    TargetImage={'S3Object': {'Bucket': S3_BUCKET_NAME, 'Name': user_kyc.s3_image_url}},
                    SimilarityThreshold=90  # Set a threshold for similarity
                )
                if response['FaceMatches']:
                    return True
        return False

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
        # Upload the image to S3
        image_hash = self._generate_image_hash(optimized_image)
        s3_key = f"selfies/{image_hash}.jpg"
        s3_client.upload_fileobj(optimized_image, S3_BUCKET_NAME, s3_key)

        # Store the S3 URL in the database
        value.s3_image_url = s3_key
        return value

    def create(self, validated_data):
        # Ensure we store the 's3_image_url' if it was generated
        image_hash = validated_data.get('selfie').image_hash

        if UserKYC.objects.filter(image_hash=image_hash).exists():
            raise serializers.ValidationError("Sorry, cannot proceed: This image has already been used. Please upload a different image.")

        # Create the UserKYC instance
        kyc = UserKYC.objects.create(**validated_data)
        kyc.image_hash = image_hash
        kyc.save()

        return kyc

    def update(self, instance, validated_data):
        # If there's a new selfie, check for duplicates again
        if 'selfie' in validated_data:
            image_hash = validated_data['selfie'].image_hash

            if UserKYC.objects.filter(image_hash=image_hash).exists():
                raise serializers.ValidationError("Sorry, cannot proceed: This image has already been used. Please upload a different image.")
            
            # Update the hash if the image is new
            instance.image_hash = image_hash

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
