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

    def _check_liveness(self, image_bytes):
    """
    Enhanced liveness detection with adjusted thresholds
    """
    try:
        response = rekognition_client.detect_faces(
            Image={'Bytes': image_bytes},
            Attributes=['ALL']
        )

        if not response['FaceDetails']:
            raise serializers.ValidationError("No face detected for liveness check.")

        face_details = response['FaceDetails'][0]

        # Basic face confidence check
        if face_details['Confidence'] < 90:
            raise serializers.ValidationError("Low confidence in face detection. Please ensure good lighting and clear image.")

        # Quality and Lighting Checks with adjusted thresholds
        quality_checks = self._perform_quality_checks(face_details)
        if not quality_checks['passed']:
            raise serializers.ValidationError(quality_checks['message'])

        # Depth Analysis with adjusted threshold
        depth_score = self._analyze_depth_information(face_details)
        if depth_score < 0.5:  # Reduced threshold from 0.8 to 0.5
            logger.warning(f"Depth score: {depth_score}")
            if depth_score < 0.3:  # Critical threshold
                raise serializers.ValidationError("Image appears to be from a flat surface. Please use a real face.")

        # Texture Analysis with adjusted threshold
        texture_score = self._analyze_facial_texture(face_details)
        if texture_score < 0.6:  # Reduced threshold from 0.75 to 0.6
            logger.warning(f"Texture score: {texture_score}")
            if texture_score < 0.4:  # Critical threshold
                raise serializers.ValidationError("Unusual facial texture detected. Please ensure this is a live face.")

        return True

    except serializers.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Liveness check error: {str(e)}")
        raise serializers.ValidationError("Failed to verify face liveness. Please try again.")

def _perform_quality_checks(self, face_details):
    """
    Adjusted quality checks with more lenient thresholds
    """
    quality_threshold = 65  # Reduced from 80
    result = {'passed': True, 'message': ''}

    # Check brightness with wider acceptable range
    brightness = face_details.get('Quality', {}).get('Brightness', 0)
    if brightness < 35 or brightness > 220:  # Adjusted range
        result['passed'] = False
        result['message'] = "Poor lighting conditions. Please ensure face is well-lit."
        return result

    # Check sharpness with lower threshold
    sharpness = face_details.get('Quality', {}).get('Sharpness', 0)
    if sharpness < quality_threshold:
        result['passed'] = False
        result['message'] = "Image is too blurry. Please provide a clearer photo."
        return result

    # Check facial landmarks
    landmarks = face_details.get('Landmarks', [])
    if len(landmarks) < 4:  # Reduced minimum landmarks requirement
        result['passed'] = False
        result['message'] = "Cannot detect clear facial features. Please retake photo."
        return result

    # More lenient symmetry check
    if not self._check_face_symmetry(landmarks):
        logger.warning("Face symmetry check failed but continuing...")
        # Don't fail immediately for symmetry issues
        pass

    return result

def _analyze_depth_information(self, face_details):
    try:
        pose = face_details.get('Pose', {})
        landmarks = face_details.get('Landmarks', [])
        
        depth_indicators = []
        
        # More lenient pose scoring
        pose_score = 1.0
        pitch = abs(pose.get('Pitch', 0))
        roll = abs(pose.get('Roll', 0))
        yaw = abs(pose.get('Yaw', 0))
        
        # Allow more natural head positioning
        if pitch < 20 and roll < 20 and yaw < 20:
            pose_score = 0.8
        elif pitch < 30 and roll < 30 and yaw < 30:
            pose_score = 0.6
        else:
            pose_score = 0.4
        
        depth_indicators.append(pose_score)

        # Enhanced landmark analysis
        if landmarks:
            nose_depth = next((l for l in landmarks if l['Type'] == 'nose'), None)
            eye_left = next((l for l in landmarks if l['Type'] == 'eyeLeft'), None)
            eye_right = next((l for l in landmarks if l['Type'] == 'eyeRight'), None)
            
            if nose_depth and eye_left and eye_right:
                depth_variance = self._calculate_depth_variance([nose_depth, eye_left, eye_right])
                depth_indicators.append(depth_variance)
                
                # Add relative position scoring
                relative_position_score = self._calculate_relative_position_score(nose_depth, eye_left, eye_right)
                depth_indicators.append(relative_position_score)

        final_score = sum(depth_indicators) / len(depth_indicators) if depth_indicators else 0.0
        logger.info(f"Depth analysis score: {final_score}")
        return final_score

    except Exception as e:
        logger.error(f"Depth analysis error: {str(e)}")
        return 0.5  # Return middle score instead of 0.0 on error

def _calculate_relative_position_score(self, nose, left_eye, right_eye):
    """
    Calculate score based on relative positions of facial features
    """
    try:
        # Check if nose is between eyes
        if left_eye['X'] < nose['X'] < right_eye['X']:
            return 0.8
        return 0.5
    except:
        return 0.5

def _analyze_facial_texture(self, face_details):
    try:
        quality = face_details.get('Quality', {})
        texture_scores = []
        
        # Adjusted sharpness scoring
        if 'Sharpness' in quality:
            sharpness = quality['Sharpness']
            if sharpness > 80:
                sharpness_score = 1.0
            elif sharpness > 60:
                sharpness_score = 0.8
            else:
                sharpness_score = sharpness / 100.0
            texture_scores.append(sharpness_score)
        
        # Adjusted brightness scoring
        if 'Brightness' in quality:
            brightness = quality['Brightness']
            if 40 <= brightness <= 200:
                brightness_score = 1.0
            else:
                brightness_score = 0.7
            texture_scores.append(brightness_score)
        
        # Landmark-based texture analysis
        landmarks = face_details.get('Landmarks', [])
        if landmarks:
            landmark_score = min(len(landmarks) / 35.0, 1.0)  # Normalized to max of 1.0
            texture_scores.append(landmark_score)

        final_score = sum(texture_scores) / len(texture_scores) if texture_scores else 0.0
        logger.info(f"Texture analysis score: {final_score}")
        return final_score

    except Exception as e:
        logger.error(f"Texture analysis error: {str(e)}")
        return 0.5  # Return middle score instead of 0.0 on error

    def _check_duplicate_faces(self, image_bytes, current_user_id=None):
        try:
            # Try to create collection if it doesn't exist
            try:
                rekognition_client.create_collection(CollectionId='user_faces_collection')
                logger.info("Face collection created or already exists")
            except rekognition_client.exceptions.ResourceAlreadyExistsException:
                pass
            except Exception as e:
                logger.error(f"Error with collection: {str(e)}")
                raise serializers.ValidationError("Error initializing face detection system")

            # Search for face in collection
            try:
                search_response = rekognition_client.search_faces_by_image(
                    CollectionId='user_faces_collection',
                    Image={'Bytes': image_bytes},
                    MaxFaces=1,
                    FaceMatchThreshold=90
                )
                
                if search_response.get('FaceMatches'):
                    logger.warning("Duplicate face found in collection")
                    return True, "This face has already been registered in our system."
                    
            except rekognition_client.exceptions.InvalidParameterException:
                logger.warning("No faces found during duplicate check")
                pass

            # Compare with existing images
            existing_kycs = UserKYC.objects.exclude(user_id=current_user_id)
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
                        SimilarityThreshold=90
                    )
                    
                    if compare_response.get('FaceMatches'):
                        logger.warning("Duplicate face found in direct comparison")
                        return True, "This face matches an existing user's verification photo."
                        
                except Exception as e:
                    logger.error(f"Error comparing faces: {str(e)}")
                    continue
            
            return False, ""
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error checking duplicate faces: {str(e)}")
            raise serializers.ValidationError("Error checking for duplicate faces. Please try again.")

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

            # Perform liveness check
            if not self._check_liveness(image_bytes):
                raise serializers.ValidationError("Failed liveness check. Please provide a live face photo.")
            value.seek(0)

            # Face analysis
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
