
from rest_framework import serializers
from .models import CustomUser
from rest_framework import serializers
from face_recognition import face_locations, face_encodings, compare_faces
import cv2
import numpy as np
import hashlib
from .models import UserKYC

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password', 'confirm_password')

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = CustomUser.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)





class UserKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserKYC
        fields = ["contact_number", "address", "country", "selfie"]

    def validate_selfie(self, value):
        selfie_image = np.array(bytearray(value.read()), dtype=np.uint8)
        img = cv2.imdecode(selfie_image, cv2.IMREAD_COLOR)
        face_locations_in_image = face_locations(img)
        if not face_locations_in_image:
            raise serializers.ValidationError("No face detected in the image.")
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < 50:
            raise serializers.ValidationError("The image appears to be a screen capture.")
        
        value.seek(0)
        md5_hash = hashlib.md5(value.read()).hexdigest()
        if UserKYC.objects.filter(image_hash=md5_hash).exists():
            raise serializers.ValidationError("Duplicate image detected.")
        
        value.image_hash = md5_hash
        return value
    





######


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import UserKYC
from .serializers import UserKYCSerializer
from .models import CustomUser
from .serializers import SignupSerializer, LoginSerializer

class SignupView(APIView):
    permission_classes = [AllowAny]

    
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(email=email, password=password)
            if user:
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }, status=status.HTTP_200_OK)
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class SubmitKYCView(generics.CreateAPIView):
    queryset = UserKYC.objects.all()
    serializer_class = UserKYCSerializer
    permission_classes = [IsAuthenticated]

