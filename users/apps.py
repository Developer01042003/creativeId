# users/apps.py
from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        try:
            from .utils import rekognition
            rekognition.create_collection()
        except Exception as e:
            print(f"Error initializing Rekognition: {str(e)}")
