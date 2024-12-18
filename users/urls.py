from django.urls import path
from .views import KYCStatusView, SignupView, LoginView, SubmitKYCView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('kyc/submit/', SubmitKYCView.as_view(), name='submit-kyc'),
    path('kyc/status/', KYCStatusView.as_view(), name='kyc-status'),
]