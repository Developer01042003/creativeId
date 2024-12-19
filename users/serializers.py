from rest_framework import serializers
from .models import UserKYC
import boto3
import hashlib
from django.conf import settings
from PIL import Image
import numpy as np
import cv2
import io
from datetime import datetime
import exifread
import magic
from deepface import DeepFace

class UserKYCSerializer(serializers.ModelSerializer):
    selfie = serializers.ImageField(required=True)

    class Meta:
        model = UserKYC
        fields = ['full_name', 'contact_number', 'address', 'country', 'selfie']

    def _check_image_metadata(self, image):
        """Check image metadata for signs of manipulation"""
        try:
            tags = exifread.process_file(image)
            
            # Check if image was modified
            if 'Image Software' in tags or 'Image PhotoshopData' in tags:
                raise serializers.ValidationError("Image appears to be edited")

            # Verify creation date if available
            if 'EXIF DateTimeOriginal' in tags:
                photo_date = datetime.strptime(str(tags['EXIF DateTimeOriginal']), '%Y:%m:%d %H:%M:%S')
                if (datetime.now() - photo_date).days > 1:
                    raise serializers.ValidationError("Image must be taken recently")

        except Exception as e:
            raise serializers.ValidationError(f"Error checking image metadata: {str(e)}")

    def _check_image_authenticity(self, image_bytes):
        """Advanced image authenticity checks"""
        try:
            # Check real file type
            file_type = magic.from_buffer(image_bytes, mime=True)
            if file_type not in ['image/jpeg', 'image/png']:
                raise serializers.ValidationError("Invalid image format")

            # Convert to numpy array for analysis
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Check for common signs of digital manipulation
            ela_img = self._error_level_analysis(img)
            if self._detect_manipulation(ela_img):
                raise serializers.ValidationError("Image appears to be manipulated")

            # Check image quality and noise patterns
            blur = cv2.Laplacian(img, cv2.CV_64F).var()
            if blur < 100:  # Threshold for blur detection
                raise serializers.ValidationError("Image is too blurry")

            # Check for screen capture or digital display
            if self._detect_screen_capture(img):
                raise serializers.ValidationError("Image appears to be a screen capture")

        except Exception as e:
            raise serializers.ValidationError(f"Image authenticity check failed: {str(e)}")

    def _error_level_analysis(self, img):
        """Perform Error Level Analysis to detect manipulation"""
        quality = 90
        _, encoded_img = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        decoded_img = cv2.imdecode(encoded_img, cv2.IMREAD_COLOR)
        return cv2.absdiff(img, decoded_img) * 10

    def _detect_manipulation(self, ela_img):
        """Analyze ELA results for signs of manipulation"""
        threshold = 50
        return np.mean(ela_img) > threshold

    def _detect_screen_capture(self, img):
        """Detect if image is a screen capture or photo of a screen"""
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply FFT to detect regular patterns
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20*np.log(np.abs(fshift))
        
        # Check for regular patterns characteristic of screens
        return np.max(magnitude_spectrum) > 1000

    def _perform_liveness_detection(self, image_bytes):
        """Perform basic liveness detection"""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Convert to different color spaces for analysis
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            
            # Check for natural skin tone variations
            skin_ycrcb_mint = np.array((0, 133, 77))
            skin_ycrcb_maxt = np.array((255, 173, 127))
            skin_ycrcb = cv2.inRange(ycrcb, skin_ycrcb_mint, skin_ycrcb_maxt)
            
            # Calculate skin percentage
            skin_ratio = np.sum(skin_ycrcb > 0) / (img.shape[0] * img.shape[1])
            if skin_ratio < 0.15:  # Adjust threshold as needed
                raise serializers.ValidationError("Natural skin tones not detected")

        except Exception as e:
            raise serializers.ValidationError(f"Liveness detection failed: {str(e)}")

    def validate_selfie(self, value):
        """Enhanced selfie validation"""
        if value.size > 10 * 1024 * 1024:  # 10MB limit
            raise serializers.ValidationError("Image size too large")
        
        try:
            # Read image data
            image_bytes = value.read()
            value.seek(0)  # Reset file pointer
            
            # Basic image validation
            img = Image.open(value)
            if img.format not in ['JPEG', 'PNG']:
                raise serializers.ValidationError("Invalid image format")
            
            # Check image dimensions
            if img.size[0] < 640 or img.size[1] < 480:
                raise serializers.ValidationError("Image resolution too low")
            
            # Metadata checks
            self._check_image_metadata(value)
            value.seek(0)
            
            # Authenticity checks
            self._check_image_authenticity(image_bytes)
            
            # Liveness detection
            self._perform_liveness_detection(image_bytes)
            
        except Exception as e:
            raise serializers.ValidationError(f"Image validation failed: {str(e)}")
        
        value.seek(0)
        return value

    def create(self, validated_data):
        user = self.context['request'].user

        # Initialize AWS clients
        rekognition = boto3.client('rekognition',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        s3 = boto3.client('s3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )

        image = validated_data['selfie']
        image_bytes = image.read()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        try:
            # Advanced face detection with AWS Rekognition
            face_detect_response = rekognition.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['ALL']
            )
            
            if not face_detect_response['FaceDetails']:
                raise serializers.ValidationError("No face detected")

            face_details = face_detect_response['FaceDetails'][0]
            
            # Enhanced face quality checks
            if face_details['Confidence'] < 95:
                raise serializers.ValidationError("Face detection confidence too low")
            
            # Check face orientation
            pose = face_details['Pose']
            if abs(pose['Yaw']) > 15 or abs(pose['Pitch']) > 15:
                raise serializers.ValidationError("Face not properly aligned")

            # Check face occlusion
            if face_details.get('Occlusions'):
                for occlusion in face_details['Occlusions']:
                    if occlusion['Value'] and occlusion['Confidence'] > 90:
                        raise serializers.ValidationError("Face must not be occluded")

            # Check sunglasses
            if face_details.get('Sunglasses', {}).get('Value', False):
                raise serializers.ValidationError("Sunglasses not allowed")

            # Check image quality attributes
            quality = face_details.get('Quality', {})
            if quality.get('Brightness', 0) < 50 or quality.get('Sharpness', 0) < 50:
                raise serializers.ValidationError("Image quality too low")

            # Use DeepFace for additional verification
            try:
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                analysis = DeepFace.analyze(img, actions=['age', 'gender', 'race', 'emotion'])
                
                # Store additional analysis results
                validated_data['face_analysis'] = analysis
            except Exception as e:
                raise serializers.ValidationError(f"Deep face analysis failed: {str(e)}")

        except Exception as e:
            raise serializers.ValidationError(f"Face validation failed: {str(e)}")

        # Compare with existing faces
        existing_kycs = UserKYC.objects.exclude(user=user).exclude(s3_image_url__isnull=True)
        
        for existing_kyc in existing_kycs:
            try:
                existing_image_key = existing_kyc.s3_image_url.split('/')[-1]
                existing_image = s3.get_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=f"kyc_selfies/{existing_kyc.user.id}/{existing_image_key}"
                )
                existing_image_bytes = existing_image['Body'].read()

                # Multiple face comparison methods
                # 1. AWS Rekognition
                compare_response = rekognition.compare_faces(
                    SourceImage={'Bytes': existing_image_bytes},
                    TargetImage={'Bytes': image_bytes},
                    SimilarityThreshold=90.0
                )

                if compare_response['FaceMatches']:
                    raise serializers.ValidationError("Face already registered")

                # 2. DeepFace comparison as backup
                try:
                    existing_img = cv2.imdecode(
                        np.frombuffer(existing_image_bytes, np.uint8),
                        cv2.IMREAD_COLOR
                    )
                    new_img = cv2.imdecode(
                        np.frombuffer(image_bytes, np.uint8),
                        cv2.IMREAD_COLOR
                    )
                    
                    verification = DeepFace.verify(
                        existing_img,
                        new_img,
                        model_name="Facenet"
                    )
                    
                    if verification['verified']:
                        raise serializers.ValidationError("Face match detected by secondary system")
                        
                except Exception:
                    pass  # Continue if DeepFace comparison fails

            except Exception as e:
                if "Face match detected" in str(e):
                    raise
                continue

        # Upload to S3 with encryption
        try:
            s3_key = f"kyc_selfies/{user.id}/{image_hash}.jpg"
            s3.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=s3_key,
                Body=image_bytes,
                ContentType='image/jpeg',
                ServerSideEncryption='AES256'
            )
            s3_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        except Exception as e:
            raise serializers.ValidationError(f"Failed to upload image: {str(e)}")

        # Create KYC record
        try:
            kyc = UserKYC.objects.create(
                user=user,
                image_hash=image_hash,
                face_confidence=face_details['Confidence'],
                s3_image_url=s3_url,
                face_analysis=validated_data.get('face_analysis'),
                **validated_data
            )
        except Exception as e:
            # Cleanup S3
            try:
                s3.delete_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key
                )
            except:
                pass
            raise serializers.ValidationError(f"Failed to create KYC record: {str(e)}")

        return kyc
