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

    def _analyze_face_details(self, image_bytes):
        """Detailed face analysis using Rekognition"""
        try:
            response = rekognition_client.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['ALL']
            )
            
            if not response['FaceDetails']:
                raise serializers.ValidationError("No face detected in the image")
            
            if len(response['FaceDetails']) > 1:
                raise serializers.ValidationError("Multiple faces detected. Please provide a selfie with only your face")
            
            face_details = response['FaceDetails'][0]
            
            # Check face quality
            quality_checks = {
                'Brightness': {'min': 30, 'max': 90},
                'Sharpness': {'min': 30, 'max': 100},
                'Confidence': {'min': 95, 'max': 100}
            }
            
            if face_details['Confidence'] < quality_checks['Confidence']['min']:
                raise serializers.ValidationError("Face detection confidence too low. Please provide a clearer photo")
            
            if face_details['Quality']['Brightness'] < quality_checks['Brightness']['min'] or \
               face_details['Quality']['Brightness'] > quality_checks['Brightness']['max']:
                raise serializers.ValidationError("Image brightness is not optimal. Please retake in better lighting")
            
            if face_details['Quality']['Sharpness'] < quality_checks['Sharpness']['min']:
                raise serializers.ValidationError("Image is not sharp enough. Please provide a clearer photo")
            
            # Check face orientation
            pose = face_details['Pose']
            max_angle = 15  # Maximum allowed angle deviation
            if abs(pose['Pitch']) > max_angle or abs(pose['Roll']) > max_angle or abs(pose['Yaw']) > max_angle:
                raise serializers.ValidationError("Face is not properly aligned. Please look straight at the camera")
            
            # Check for sunglasses
            if face_details.get('Sunglasses', {}).get('Value', False):
                raise serializers.ValidationError("Please remove sunglasses")
            
            # Check eyes
            if not face_details.get('EyesOpen', {}).get('Value', False):
                raise serializers.ValidationError("Please keep your eyes open")
            
            # Check for face occlusion
            if face_details.get('Occlusions', {}).get('Value', False):
                raise serializers.ValidationError("Face is partially covered. Please remove any obstacles")
            
            return face_details
            
        except Exception as e:
            logger.error(f"Error in face analysis: {str(e)}")
            raise serializers.ValidationError("Error analyzing face details")

    def _generate_face_embedding(self, image_bytes):
        """Generate face embedding using Rekognition"""
        try:
            response = rekognition_client.index_faces(
                CollectionId='user_faces_collection',
                Image={'Bytes': image_bytes},
                MaxFaces=1,
                QualityFilter="HIGH",
                DetectionAttributes=['ALL']
            )
            
            if not response.get('FaceRecords'):
                raise serializers.ValidationError("Failed to generate face embedding")
            
            face_record = response['FaceRecords'][0]
            
            # Clean up the indexed face immediately as we only need the embedding
            rekognition_client.delete_faces(
                CollectionId='user_faces_collection',
                FaceIds=[face_record['Face']['FaceId']]
            )
            
            return face_record['Face']['FaceId']
            
        except Exception as e:
            logger.error(f"Error generating face embedding: {str(e)}")
            raise serializers.ValidationError("Error processing face recognition")

    def _check_duplicate_faces(self, image_bytes, current_user_id=None):
        """Enhanced duplicate face detection"""
        try:
            # First, check using Rekognition's face search
            response = rekognition_client.search_faces_by_image(
                CollectionId='user_faces_collection',
                Image={'Bytes': image_bytes},
                MaxFaces=5,  # Check multiple potential matches
                FaceMatchThreshold=80  # Stricter threshold
            )
            
            if response['FaceMatches']:
                for match in response['FaceMatches']:
                    if match['Similarity'] > 80:  # Additional similarity threshold
                        existing_kyc = UserKYC.objects.filter(
                            face_id=match['Face']['FaceId']
                        ).exclude(user_id=current_user_id).first()
                        
                        if existing_kyc:
                            return True

            # Additional check using compare_faces for extra verification
            existing_kycs = UserKYC.objects.exclude(user_id=current_user_id)
            for existing_kyc in existing_kycs:
                try:
                    compare_response = rekognition_client.compare_faces(
                        SourceImage={'Bytes': image_bytes},
                        TargetImage={'S3Object': {
                            'Bucket': S3_BUCKET_NAME,
                            'Name': existing_kyc.s3_image_url
                        }},
                        SimilarityThreshold=80
                    )
                    
                    if compare_response['FaceMatches']:
                        for face_match in compare_response['FaceMatches']:
                            if face_match['Similarity'] > 80:
                                return True
                                
                except Exception as e:
                    logger.error(f"Error in compare_faces: {str(e)}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking duplicate faces: {str(e)}")
            raise serializers.ValidationError("Error checking for duplicate faces")

    def validate_selfie(self, value):
        try:
            current_user_id = self.instance.user_id if self.instance else None

            if not isinstance(value, InMemoryUploadedFile):
                raise serializers.ValidationError("Invalid image format")

            # Read image data
            image_bytes = value.read()
            image = Image.open(io.BytesIO(image_bytes))
            value.seek(0)

            # Basic image validations
            width, height = image.size
            min_dimension = 500  # Increased minimum resolution
            if width < min_dimension or height < min_dimension:
                raise serializers.ValidationError(
                    f"Image resolution too low. Minimum {min_dimension}x{min_dimension} pixels required."
                )

            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Image size too large. Maximum 5MB allowed.")

            # Validate image format
            allowed_formats = ['JPEG', 'JPG', 'PNG']
            if image.format.upper() not in allowed_formats:
                raise serializers.ValidationError(f"Invalid image format. Allowed formats: {', '.join(allowed_formats)}")

            # Detailed face analysis
            face_details = self._analyze_face_details(image_bytes)
            value.seek(0)

            # Check for duplicate faces
            if self._check_duplicate_faces(image_bytes, current_user_id):
                raise serializers.ValidationError(
                    "This face has already been registered. Please verify your identity."
                )
            value.seek(0)

            # Generate face embedding
            face_id = self._generate_face_embedding(image_bytes)
            value.seek(0)

            # Process and optimize image
            optimized_image = self._compress_image(image)
            image_hash = self._generate_image_hash(optimized_image)

            # Store metadata
            value.face_id = face_id
            value.image_hash = image_hash
            value.face_confidence = face_details['Confidence']

            return self._save_image(optimized_image, value)

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise serializers.ValidationError("Error processing image. Please try again.")

    def _compress_image(self, image):
        """Enhanced image compression"""
        try:
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Resize if too large while maintaining aspect ratio
            max_dimension = 1500
            if image.width > max_dimension or image.height > max_dimension:
                image.thumbnail((max_dimension, max_dimension))

            # Apply some enhancement
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.2)

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85, optimize=True)
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"Error compressing image: {str(e)}")
            raise serializers.ValidationError("Error processing image")

    def create(self, validated_data):
        try:
            # Additional validation before creation
            selfie = validated_data.get('selfie')
            if UserKYC.objects.filter(face_id=selfie.face_id).exists():
                raise serializers.ValidationError("Face already registered in the system")

            # Create the UserKYC instance
            kyc = UserKYC.objects.create(
                **validated_data,
                face_id=selfie.face_id,
                image_hash=selfie.image_hash,
                face_confidence=selfie.face_confidence
            )

            return kyc

        except Exception as e:
            logger.error(f"Error creating UserKYC: {str(e)}")
            raise serializers.ValidationError("Error creating user verification")
