from rest_framework import serializers
from .models import CustomUser, UserKYC
import boto3
import hashlib
import io
import logging
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.cache import cache

logger = logging.getLogger(__name__)

# AWS Configuration
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

S3_BUCKET_NAME = 'imagingkyc'

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

import boto3
import io
import hashlib
from PIL import Image
from django.core.cache import cache
from rest_framework import serializers
from django.core.files.uploadedfile import InMemoryUploadedFile

# Initialize the Rekognition client


class UserKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserKYC
        fields = ['full_name', 'contact_number', 'address', 'country', 'selfie']

    def _analyze_face_details(self, image_bytes):
        try:
            response = rekognition_client.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['ALL']
            )

            if not response['FaceDetails']:
                raise serializers.ValidationError("No face detected in the image. Please provide a clear photo of your face.")

            if len(response['FaceDetails']) > 1:
                raise serializers.ValidationError("Multiple faces detected. Please provide a selfie with only your face.")

            face_details = response['FaceDetails'][0]

            # Quality checks
            if face_details['Confidence'] < 70:
                raise serializers.ValidationError("Face detection confidence too low. Please provide a clearer photo in good lighting.")

            # Check face orientation
            pose = face_details['Pose']
            max_angle = 15
            if abs(pose['Pitch']) > max_angle or abs(pose['Roll']) > max_angle or abs(pose['Yaw']) > max_angle:
                raise serializers.ValidationError("Face is not properly aligned. Please look straight at the camera.")

            # Check eyes
            if not face_details.get('EyesOpen', {}).get('Value', False):
                raise serializers.ValidationError("Please keep your eyes open in the photo.")

            # Check for sunglasses
            if face_details.get('Sunglasses', {}).get('Value', True):
                raise serializers.ValidationError("Please remove sunglasses.")

            return face_details

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in face analysis: {str(e)}")
            raise serializers.ValidationError("Error analyzing face details. Please try again with a clearer photo.")

    def _check_duplicate_faces(self, image_bytes, current_user_id=None):
    try:
        # Step 1: Initialize Collection with Error Handling
        try:
            collection_response = rekognition_client.create_collection(
                CollectionId='user_faces_collection',
                Tags={
                    'Environment': 'Production',
                    'Purpose': 'KYC-Verification'
                }
            )
            logger.info(f"Collection status: {collection_response['StatusCode']}")
        except rekognition_client.exceptions.ResourceAlreadyExistsException:
            logger.info("Using existing face collection")
        except Exception as e:
            logger.error(f"Collection initialization error: {str(e)}")
            raise serializers.ValidationError("System initialization error. Please try again.")

        # Step 2: Enhanced Face Quality Pre-check
        face_analysis = rekognition_client.detect_faces(
            Image={'Bytes': image_bytes},
            Attributes=['QUALITY', 'POSE']
        )

        if not face_analysis.get('FaceDetails'):
            raise serializers.ValidationError("No clear face detected. Please provide a better quality photo.")

        face_quality = face_analysis['FaceDetails'][0].get('Quality', {})
        if face_quality.get('Brightness', 0) < 40 or face_quality.get('Sharpness', 0) < 40:
            raise serializers.ValidationError("Poor image quality. Please provide a clearer photo.")

        # Step 3: Advanced Similarity Search in Collection
        try:
            search_response = rekognition_client.search_faces_by_image(
                CollectionId='user_faces_collection',
                Image={'Bytes': image_bytes},
                MaxFaces=5,  # Increased to check multiple potential matches
                FaceMatchThreshold=85  # Slightly lower threshold to catch near-matches
            )

            if search_response.get('FaceMatches'):
                matches = search_response['FaceMatches']
                # Analyze all matches
                for match in matches:
                    similarity = match.get('Similarity', 0)
                    face_id = match.get('Face', {}).get('FaceId')
                    
                    logger.warning(f"Face match found - Similarity: {similarity}%, FaceId: {face_id}")
                    
                    if similarity >= 90:
                        return True, "This face has already been registered in our system."
                    elif similarity >= 85:
                        logger.warning(f"Near-duplicate face detected with {similarity}% similarity")
                        return True, "A very similar face is already registered in our system."

        except rekognition_client.exceptions.InvalidParameterException as e:
            logger.warning(f"Face search parameter error: {str(e)}")
        except Exception as e:
            logger.error(f"Face search error: {str(e)}")
            raise serializers.ValidationError("Error during face verification. Please try again.")

        # Step 4: Enhanced Direct Comparison with Existing Images
        existing_kycs = UserKYC.objects.exclude(user_id=current_user_id).filter(
            face_confidence__gte=90  # Only compare with high-confidence existing images
        )

        for existing_kyc in existing_kycs:
            if not existing_kyc.s3_image_url:
                continue

            try:
                compare_response = rekognition_client.compare_faces(
                    SourceImage={'Bytes': image_bytes},
                    TargetImage={'S3Object': {
                        'Bucket': S3_BUCKET_NAME,
                        'Name': existing_kyc.s3_image_url
                    }},
                    SimilarityThreshold=85,  # Catch near-matches
                    QualityFilter='HIGH'
                )

                if compare_response.get('FaceMatches'):
                    for match in compare_response['FaceMatches']:
                        similarity = match.get('Similarity', 0)
                        
                        # Log detailed match information
                        logger.warning(
                            f"Direct comparison match found - "
                            f"Similarity: {similarity}%, "
                            f"User ID: {existing_kyc.user_id}, "
                            f"Confidence: {match.get('Face', {}).get('Confidence')}%"
                        )

                        if similarity >= 90:
                            # Record the attempt for security monitoring
                            self._record_duplicate_attempt(
                                current_user_id, 
                                existing_kyc.user_id, 
                                similarity
                            )
                            return True, "This face matches an existing user's verification photo."
                        elif similarity >= 85:
                            return True, "A very similar face is already registered in our system."

            except Exception as e:
                logger.error(f"Face comparison error: {str(e)}")
                continue

        # Step 5: Final Security Check
        if self._check_suspicious_activity(current_user_id):
            raise serializers.ValidationError(
                "Multiple verification attempts detected. Please try again later."
            )

        return False, ""

    except serializers.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Duplicate check error: {str(e)}")
        raise serializers.ValidationError(
            "Unable to complete face verification. Please try again later."
        )

def _record_duplicate_attempt(self, current_user_id, matched_user_id, similarity):
    """Record duplicate face detection attempts for security monitoring"""
    try:
        cache_key = f'duplicate_attempts_{current_user_id}'
        attempts = cache.get(cache_key, [])
        attempts.append({
            'timestamp': datetime.now().isoformat(),
            'matched_user_id': matched_user_id,
            'similarity': similarity
        })
        cache.set(cache_key, attempts, timeout=86400)  # Store for 24 hours

        if len(attempts) >= 3:
            logger.critical(
                f"Multiple duplicate attempts detected for user {current_user_id}"
            )
            # You might want to implement additional security measures here
    except Exception as e:
        logger.error(f"Error recording duplicate attempt: {str(e)}")

def _check_suspicious_activity(self, user_id):
    """Check for suspicious verification attempts"""
    try:
        attempts = cache.get(f'duplicate_attempts_{user_id}', [])
        recent_attempts = [
            a for a in attempts 
            if (datetime.now() - datetime.fromisoformat(a['timestamp'])).seconds < 3600
        ]
        return len(recent_attempts) >= 3
    except Exception as e:
        logger.error(f"Error checking suspicious activity: {str(e)}")
        return False

def _check_face_liveness(self, image_bytes):
    try:
        # Basic face detection
        response = rekognition_client.detect_faces(
            Image={'Bytes': image_bytes},
            Attributes=['ALL']
        )

        if not response.get('FaceDetails'):
            raise serializers.ValidationError(
                "No face detected. Please take a clear photo of your face."
            )

        face_details = response['FaceDetails'][0]

        # Basic quality checks
        quality = face_details.get('Quality', {})
        confidence = face_details.get('Confidence', 0)

        # More lenient thresholds
        if confidence < 80:  # Reduced from 90
            raise serializers.ValidationError(
                "Please take a clearer photo of your face."
            )

        # Check basic face attributes
        if face_details.get('Sunglasses', {}).get('Value', False):
            raise serializers.ValidationError(
                "Please remove sunglasses."
            )

        if not face_details.get('EyesOpen', {}).get('Value', False):
            raise serializers.ValidationError(
                "Please keep your eyes open."
            )

        # Check face orientation with more lenient angles
        pose = face_details.get('Pose', {})
        max_angle = 20  # Increased from 15
        if (abs(pose.get('Pitch', 0)) > max_angle or 
            abs(pose.get('Roll', 0)) > max_angle or 
            abs(pose.get('Yaw', 0)) > max_angle):
            raise serializers.ValidationError(
                "Please look directly at the camera."
            )

        # If all checks pass, consider it a valid photo
        return True

    except serializers.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error in liveness detection: {str(e)}")
        raise serializers.ValidationError(
            "Unable to verify photo. Please take a clear photo in good lighting."
        )

    def validate_selfie(self, value):
        try:
            if not isinstance(value, InMemoryUploadedFile):
                raise serializers.ValidationError("Invalid image format. Please upload a valid image file.")

            # Read image data
            image_bytes = value.read()
            image = Image.open(io.BytesIO(image_bytes))
            value.seek(0)

            # Basic image validations
            width, height = image.size
            if width < 200 or height < 200:
                raise serializers.ValidationError(
                    "Image resolution too low. Minimum 200x200 pixels required."
                )

            # Check file size (max 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(
                    "Image size too large. Maximum 10MB allowed."
                )

            # Validate image format
            if image.format.upper() not in ['JPEG', 'JPG', 'PNG']:
                raise serializers.ValidationError(
                    "Invalid image format. Please upload a JPEG or PNG image."
                )

            # Add rate limiting check
            user_id = self.context.get('user_id')
            cache_key = f'liveness_check_{user_id}'
            if cache.get(cache_key):
                raise serializers.ValidationError(
                    "Please wait 30 seconds before trying another photo upload."
                )
            cache.set(cache_key, True, 30)

            # Check face liveness first
            is_live = self._check_face_liveness(image_bytes)
            value.seek(0)

            if not is_live:
                raise serializers.ValidationError(
                    "Unable to verify photo authenticity. Please take a real-time photo."
                )

            # Continue with existing validations
            face_details = self._analyze_face_details(image_bytes)
            value.seek(0)

            # Check for duplicates
            is_duplicate, error_message = self._check_duplicate_faces(
                image_bytes,
                self.context.get('user_id')
            )

            if is_duplicate:
                raise serializers.ValidationError(error_message)

            value.seek(0)

            try:
                # Index the face
                index_response = rekognition_client.index_faces(
                    CollectionId='user_faces_collection',
                    Image={'Bytes': image_bytes},
                    MaxFaces=1,
                    QualityFilter="HIGH",
                    DetectionAttributes=['ALL']
                )

                if not index_response.get('FaceRecords'):
                    raise serializers.ValidationError(
                        "Failed to process face. Please try again with a clearer photo."
                    )

                face_id = index_response['FaceRecords'][0]['Face']['FaceId']

                # Generate image hash and compress
                optimized_image = self._compress_image(image)
                image_hash = hashlib.sha256(optimized_image.getvalue()).hexdigest()

                # Store metadata
                value.face_id = face_id
                value.image_hash = image_hash
                value.face_confidence = face_details['Confidence']

                # Upload to S3
                s3_key = f"selfies/{face_id}.jpg"
                s3_client.upload_fileobj(
                    optimized_image,
                    S3_BUCKET_NAME,
                    s3_key,
                    ExtraArgs={'ContentType': 'image/jpeg'}
                )
                value.s3_image_url = s3_key

                return value

            except Exception as e:
                # Clean up indexed face if there's an error
                if 'face_id' in locals():
                    try:
                        rekognition_client.delete_faces(
                            CollectionId='user_faces_collection',
                            FaceIds=[face_id]
                        )
                    except Exception as del_e:
                        logger.error(f"Error cleaning up indexed face: {str(del_e)}")

                logger.error(f"Error processing image: {str(e)}")
                raise serializers.ValidationError(
                    "Error processing image. Please try again with a different photo."
                )

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in validate_selfie: {str(e)}")
            raise serializers.ValidationError(
                "Error processing image. Please try again."
            )

    def _compress_image(self, image):
        try:
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Resize if needed while maintaining aspect ratio
            max_size = 1024
            if image.width > max_size or image.height > max_size:
                image.thumbnail((max_size, max_size))

            # Compress
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85, optimize=True)
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"Error compressing image: {str(e)}")
            raise serializers.ValidationError("Error processing image. Please try again.")

    def create(self, validated_data):
        try:
            # Double-check for duplicate face_id
            face_id = getattr(validated_data.get('selfie'), 'face_id', None)
            if face_id and UserKYC.objects.filter(face_id=face_id).exists():
                # Clean up the indexed face
                try:
                    rekognition_client.delete_faces(
                        CollectionId='user_faces_collection',
                        FaceIds=[face_id]
                    )
                except Exception as e:
                    logger.error(f"Error cleaning up face index: {str(e)}")

                raise serializers.ValidationError(
                    "This face has already been registered in our system."
                )

            # Create KYC record
            kyc = UserKYC.objects.create(
                **validated_data,
                face_id=getattr(validated_data['selfie'], 'face_id', None),
                image_hash=getattr(validated_data['selfie'], 'image_hash', None),
                face_confidence=getattr(validated_data['selfie'], 'face_confidence', None),
                s3_image_url=getattr(validated_data['selfie'], 's3_image_url', None)
            )

            return kyc

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating KYC: {str(e)}")
            # Clean up any indexed face if creation fails
            face_id = getattr(validated_data.get('selfie'), 'face_id', None)
            if face_id:
                try:
                    rekognition_client.delete_faces(
                        CollectionId='user_faces_collection',
                        FaceIds=[face_id]
                    )
                except Exception as del_e:
                    logger.error(f"Error cleaning up face index: {str(del_e)}")

            raise serializers.ValidationError("Error creating KYC record. Please try again.")
