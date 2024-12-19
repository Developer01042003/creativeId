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

S3_BUCKET_NAME = 'imagingkyccc'

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
            if face_details['Confidence'] < 90:
                raise serializers.ValidationError("Face detection confidence too low. Please provide a clearer photo in good lighting.")
            
            # Check face orientation
            pose = face_details['Pose']
            max_angle = 20  # Increased from 15
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

    def _check_liveness(self, image_bytes):
        try:
            response = rekognition_client.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['ALL']
            )

            if not response['FaceDetails']:
                raise serializers.ValidationError("No face detected for liveness check.")

            face_details = response['FaceDetails'][0]

            # Basic face confidence check
            if face_details['Confidence'] < 85:  # Reduced from 90
                raise serializers.ValidationError("Low confidence in face detection. Please ensure good lighting and clear image.")

            # Quality and Lighting Checks
            quality_checks = self._perform_quality_checks(face_details)
            if not quality_checks['passed']:
                raise serializers.ValidationError(quality_checks['message'])

            # Depth Analysis
            depth_score = self._analyze_depth_information(face_details)
            logger.info(f"Depth score: {depth_score}")
            if depth_score < 0.4:  # Reduced threshold
                raise serializers.ValidationError("Please ensure you're using a real face photo.")

            # Texture Analysis
            texture_score = self._analyze_facial_texture(face_details)
            logger.info(f"Texture score: {texture_score}")
            if texture_score < 0.5:  # Reduced threshold
                raise serializers.ValidationError("Please provide a clearer photo with good lighting.")

            return True

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Liveness check error: {str(e)}")
            return True  # More permissive error handling

    def _perform_quality_checks(self, face_details):
        quality_threshold = 60  # Reduced from 65
        result = {'passed': True, 'message': ''}

        # Check brightness with wider range
        brightness = face_details.get('Quality', {}).get('Brightness', 0)
        if brightness < 30 or brightness > 230:  # Wider range
            result['passed'] = False
            result['message'] = "Please ensure face is well-lit."
            return result

        # Check sharpness
        sharpness = face_details.get('Quality', {}).get('Sharpness', 0)
        if sharpness < quality_threshold:
            result['passed'] = False
            result['message'] = "Image is too blurry. Please provide a clearer photo."
            return result

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
            
            if pitch < 25 and roll < 25 and yaw < 25:
                pose_score = 0.8
            elif pitch < 35 and roll < 35 and yaw < 35:
                pose_score = 0.6
            else:
                pose_score = 0.4
            
            depth_indicators.append(pose_score)

            return sum(depth_indicators) / len(depth_indicators) if depth_indicators else 0.5

        except Exception as e:
            logger.error(f"Depth analysis error: {str(e)}")
            return 0.5

    def _analyze_facial_texture(self, face_details):
        try:
            quality = face_details.get('Quality', {})
            texture_scores = []
            
            if 'Sharpness' in quality:
                sharpness = quality['Sharpness']
                sharpness_score = min((sharpness / 80.0), 1.0)  # More lenient scoring
                texture_scores.append(sharpness_score)
            
            if 'Brightness' in quality:
                brightness = quality['Brightness']
                if 35 <= brightness <= 220:
                    brightness_score = 1.0
                else:
                    brightness_score = 0.7
                texture_scores.append(brightness_score)

            return sum(texture_scores) / len(texture_scores) if texture_scores else 0.5

        except Exception as e:
            logger.error(f"Texture analysis error: {str(e)}")
            return 0.5

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

            # Get all objects from S3 bucket
            try:
                s3_objects = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME)
                
                # Compare with each image in S3
                for obj in s3_objects.get('Contents', []):
                    if not obj['Key'].startswith('selfies/'):
                        continue
                    
                    try:
                        compare_response = rekognition_client.compare_faces(
                            SourceImage={'Bytes': image_bytes},
                            TargetImage={
                                'S3Object': {
                                    'Bucket': S3_BUCKET_NAME,
                                    'Name': obj['Key']
                                }
                            },
                            SimilarityThreshold=90
                        )
                        
                        if compare_response.get('FaceMatches'):
                            similarity = compare_response['FaceMatches'][0]['Similarity']
                            logger.warning(f"Duplicate face found in S3 with similarity: {similarity}%")
                            return True, "This face matches an existing user's verification photo."
                            
                    except rekognition_client.exceptions.InvalidParameterException:
                        logger.warning(f"No face found in image: {obj['Key']}")
                        continue
                    except Exception as e:
                        logger.error(f"Error comparing faces with {obj['Key']}: {str(e)}")
                        continue

                # If no matches found in S3, check collection as backup
                try:
                    search_response = rekognition_client.search_faces_by_image(
                        CollectionId='user_faces_collection',
                        Image={'Bytes': image_bytes},
                        MaxFaces=1,
                        FaceMatchThreshold=90
                    )
                    
                    if search_response.get('FaceMatches'):
                        similarity = search_response['FaceMatches'][0]['Similarity']
                        logger.warning(f"Duplicate face found in collection with similarity: {similarity}%")
                        return True, "This face has already been registered in our system."
                        
                except rekognition_client.exceptions.InvalidParameterException:
                    logger.warning("No faces found during collection check")
                    pass
                except Exception as e:
                    logger.error(f"Error searching in collection: {str(e)}")
                    pass
                
                return False, ""
                
            except Exception as e:
                logger.error(f"Error listing S3 objects: {str(e)}")
                raise serializers.ValidationError("Error accessing image storage system")
                
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
            if image.mode != 'RGB':
                image = image.convert('RGB')

            max_size = 1024
            if image.width > max_size or image.height > max_size:
                image.thumbnail((max_size, max_size))

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85, optimize=True)
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"Error compressing image: {str(e)}")
            raise serializers.ValidationError("Error processing image. Please try again.")

    def create(self, validated_data):
        try:
            kyc = UserKYC.objects.create(
                **validated_data,
                face_id=getattr(validated_data['selfie'], 'face_id', None),
                image_hash=getattr(validated_data['selfie'], 'image_hash', None),
                face_confidence=getattr(validated_data['selfie'], 'face_confidence', None),
                s3_image_url=getattr(validated_data['selfie'], 's3_image_url', None)
            )
            return kyc

        except Exception as e:
            logger.error(f"Error creating KYC: {str(e)}")
            raise serializers.ValidationError("Error creating KYC record. Please try again.")
