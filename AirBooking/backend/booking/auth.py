from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def eligible(user):
    return user.is_active and (user.is_superuser or user.approval_status == user.Approval.APPROVED)


class ApprovedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not eligible(user):
            raise AuthenticationFailed("This account is no longer approved.")
        return user
