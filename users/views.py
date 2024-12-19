from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from .models import UserKYC, CustomUser
from .serializers import UserKYCSerializer, SignupSerializer, LoginSerializer
import logging

logger = logging.getLogger(__name__)

class BaseAPIView(APIView):
    """Base API View with common error handling"""
    
    def handle_exception(self, exc):
        logger.error(f"Error in {self.__class__.__name__}: {str(exc)}", exc_info=True)
        
        if isinstance(exc, ValidationError):
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {"error": "An unexpected error occurred. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class SignupView(BaseAPIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        try:
            logger.info("Processing signup request")
            serializer = SignupSerializer(data=request.data)
            
            if not serializer.is_valid():
                logger.warning(f"Invalid signup data: {serializer.errors}")
                return Response({
                    'error': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            
            logger.info(f"User created successfully: {user.email}")
            return Response({
                'message': 'User created successfully',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': {
                    'email': user.email,
                    'username': user.username,
                    'is_kyc': user.is_kyc,
                    'is_submitted': user.is_submitted,
                    'is_rejected': user.is_rejected,
                    'rejection_times': user.rejection_times,
                    'unique_id': str(user.unique_id)
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Signup error: {str(e)}", exc_info=True)
            return self.handle_exception(e)

class LoginView(BaseAPIView):
    permission_classes = [AllowAny]

    @method_decorator(never_cache)
    def post(self, request):
        try:
            logger.info("Processing login request")
            serializer = LoginSerializer(data=request.data)
            
            if not serializer.is_valid():
                logger.warning(f"Invalid login data: {serializer.errors}")
                return Response({
                    'error': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            user = authenticate(request, email=email, password=password)
            
            if user is None:
                logger.warning(f"Failed login attempt for email: {email}")
                return Response({
                    "error": "Invalid credentials"
                }, status=status.HTTP_401_UNAUTHORIZED)

            refresh = RefreshToken.for_user(user)
            logger.info(f"Successful login for user: {email}")
            
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': {
                    'email': user.email,
                    'username': user.username,
                    'is_kyc': user.is_kyc,
                    'is_submitted': user.is_submitted,
                    'is_rejected': user.is_rejected,
                    'rejection_times': user.rejection_times,
                    'unique_id': str(user.unique_id)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            return self.handle_exception(e)

class SubmitKYCView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            logger.info(f"Processing KYC submission for user: {request.user.email}")
            
            # Check if user has already submitted KYC
            if request.user.is_submitted:
                status_msg = "PENDING" if not request.user.is_rejected else "REJECTED"
                logger.warning(f"Duplicate KYC submission attempt for user: {request.user.email}")
                return Response({
                    "error": "KYC already submitted",
                    "status": status_msg
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check rejection limit
            if request.user.rejection_times >= 3:
                logger.warning(f"Maximum KYC attempts reached for user: {request.user.email}")
                return Response({
                    "error": "Maximum KYC submission attempts reached"
                }, status=status.HTTP_400_BAD_REQUEST)

            serializer = UserKYCSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"Invalid KYC data: {serializer.errors}")
                return Response({
                    "error": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            kyc = serializer.save(user=request.user)
            
            # Update user status
            request.user.is_submitted = True
            request.user.is_rejected = False
            request.user.save()

            logger.info(f"KYC submitted successfully for user: {request.user.email}")
            return Response({
                "message": "KYC submitted successfully",
                "data": {
                    "full_name": kyc.full_name,
                    "contact_number": kyc.contact_number,
                    "status": "PENDING",
                    "submitted_at": kyc.created_at
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"KYC submission error: {str(e)}", exc_info=True)
            return self.handle_exception(e)

    def get(self, request):
        try:
            logger.info(f"Fetching KYC details for user: {request.user.email}")
            kyc = UserKYC.objects.select_related('user').get(user=request.user)
            
            serializer = UserKYCSerializer(kyc)
            return Response({
                "data": serializer.data,
                "user_status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                }
            }, status=status.HTTP_200_OK)
            
        except UserKYC.DoesNotExist:
            logger.info(f"No KYC found for user: {request.user.email}")
            return Response({
                "error": "KYC not found",
                "user_status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                }
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching KYC: {str(e)}", exc_info=True)
            return self.handle_exception(e)

class KYCStatusView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            logger.info(f"Fetching KYC status for user: {request.user.email}")
            kyc = UserKYC.objects.select_related('user').get(user=request.user)
            
            return Response({
                "status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times,
                    "verification_status": kyc.verification_status
                },
                "kyc_data": {
                    "full_name": kyc.full_name,
                    "contact_number": kyc.contact_number,
                    "address": kyc.address,
                    "country": kyc.country,
                    "submitted_at": kyc.created_at,
                    "last_updated": kyc.updated_at,
                    "rejection_reason": kyc.rejection_reason if kyc.is_rejected else None
                }
            }, status=status.HTTP_200_OK)
            
        except UserKYC.DoesNotExist:
            logger.info(f"No KYC found for user: {request.user.email}")
            return Response({
                "status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                },
                "message": "KYC not submitted yet"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching KYC status: {str(e)}", exc_info=True)
            return self.handle_exception(e)
