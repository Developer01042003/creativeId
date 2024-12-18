from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import UserKYC, CustomUser
from .serializers import UserKYCSerializer, SignupSerializer, LoginSerializer

class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            print("Received signup data:", request.data)  # Debug print
            serializer = SignupSerializer(data=request.data)
            
            if serializer.is_valid():
                print("Serializer is valid")  # Debug print
                user = serializer.save()
                refresh = RefreshToken.for_user(user)
                
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
            
            print("Serializer errors:", serializer.errors)  # Debug print
            return Response({
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print("Exception during signup:", str(e))  # Debug print
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            print("Received login data:", request.data)  # Debug print
            serializer = LoginSerializer(data=request.data)
            
            if serializer.is_valid():
                email = serializer.validated_data['email']
                password = serializer.validated_data['password']
                
                user = authenticate(request, email=email, password=password)
                print(f"Authentication result for {email}:", user)  # Debug print
                
                if user is not None:
                    refresh = RefreshToken.for_user(user)
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
                
                return Response({
                    "error": "Invalid credentials"
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            print("Login serializer errors:", serializer.errors)  # Debug print
            return Response({
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print("Exception during login:", str(e))  # Debug print
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SubmitKYCView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Check if user has already submitted KYC
            if request.user.is_submitted:
                return Response({
                    "error": "KYC already submitted",
                    "status": "PENDING" if not request.user.is_rejected else "REJECTED"
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check rejection limit
            if request.user.rejection_times >= 3:
                return Response({
                    "error": "Maximum KYC submission attempts reached"
                }, status=status.HTTP_400_BAD_REQUEST)

            serializer = UserKYCSerializer(data=request.data)
            if serializer.is_valid():
                kyc = serializer.save(user=request.user)
                
                # Update user status
                request.user.is_submitted = True
                request.user.is_rejected = False
                request.user.save()

                return Response({
                    "message": "KYC submitted successfully",
                    "data": {
                        "full_name": kyc.full_name,
                        "contact_number": kyc.contact_number,
                        "status": "PENDING",
                        "submitted_at": kyc.created_at
                    }
                }, status=status.HTTP_201_CREATED)
            
            return Response({
                "error": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print("Exception during KYC submission:", str(e))  # Debug print
            return Response({
                "error": f"Error processing KYC: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        try:
            kyc = UserKYC.objects.get(user=request.user)
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
            return Response({
                "error": "KYC not found",
                "user_status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                }
            }, status=status.HTTP_404_NOT_FOUND)
        
class KYCStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            kyc = UserKYC.objects.get(user=request.user)
            return Response({
                "status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                },
                "kyc_data": {
                    "full_name": kyc.full_name,
                    "contact_number": kyc.contact_number,
                    "address": kyc.address,
                    "country": kyc.country,
                    "submitted_at": kyc.created_at,
                    "last_updated": kyc.updated_at
                }
            }, status=status.HTTP_200_OK)
        except UserKYC.DoesNotExist:
            return Response({
                "status": {
                    "is_kyc": request.user.is_kyc,
                    "is_submitted": request.user.is_submitted,
                    "is_rejected": request.user.is_rejected,
                    "rejection_times": request.user.rejection_times
                },
                "message": "KYC not submitted yet"
            }, status=status.HTTP_200_OK)