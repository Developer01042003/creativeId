# users/utils.py
import boto3
import logging
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

class AWSRekognition:
    def __init__(self):
        self.client = boto3.client(
            'rekognition',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        self.collection_id = 'user_faces_collection'

    def create_collection(self):
        """Create a collection if it doesn't exist"""
        try:
            self.client.create_collection(CollectionId=self.collection_id)
            logger.info(f"Collection {self.collection_id} created")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                logger.info(f"Collection {self.collection_id} already exists")
                return True
            logger.error(f"Error creating collection: {str(e)}")
            return False

    def delete_collection(self):
        """Delete a collection"""
        try:
            self.client.delete_collection(CollectionId=self.collection_id)
            logger.info(f"Collection {self.collection_id} deleted")
            return True
        except ClientError as e:
            logger.error(f"Error deleting collection: {str(e)}")
            return False

    def index_face(self, image_bytes):
        """Index a face and return the face ID"""
        try:
            response = self.client.index_faces(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                MaxFaces=1,
                QualityFilter="HIGH",
                DetectionAttributes=['ALL']
            )
            
            if not response.get('FaceRecords'):
                logger.warning("No face detected in the image")
                return None
                
            return response['FaceRecords'][0]['Face']['FaceId']
        except ClientError as e:
            logger.error(f"Error indexing face: {str(e)}")
            return None

    def search_faces(self, image_bytes):
        """Search for similar faces"""
        try:
            response = self.client.search_faces_by_image(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                MaxFaces=1,
                FaceMatchThreshold=90
            )
            return response.get('FaceMatches', [])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Create collection if it doesn't exist
                if self.create_collection():
                    # Retry the search
                    return self.search_faces(image_bytes)
            logger.error(f"Error searching faces: {str(e)}")
            return []

    def detect_faces(self, image_bytes):
        """Detect faces and their attributes"""
        try:
            response = self.client.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['ALL']
            )
            return response.get('FaceDetails', [])
        except ClientError as e:
            logger.error(f"Error detecting faces: {str(e)}")
            return []

    def compare_faces(self, source_image, target_image):
        """Compare two faces"""
        try:
            response = self.client.compare_faces(
                SourceImage={'Bytes': source_image},
                TargetImage={'Bytes': target_image},
                SimilarityThreshold=90
            )
            return response.get('FaceMatches', [])
        except ClientError as e:
            logger.error(f"Error comparing faces: {str(e)}")
            return []

# Create a singleton instance
rekognition = AWSRekognition()
