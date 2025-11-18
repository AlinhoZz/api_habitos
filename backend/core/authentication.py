from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions

from .models import Usuario


def create_jwt_for_user(user: Usuario) -> str:

    now = datetime.now(timezone.utc)
    lifetime_minutes = getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 15)
    exp = now + timedelta(minutes=lifetime_minutes)

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token


class JWTAuthentication(BaseAuthentication):

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None 

        parts = auth_header.split()

        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            return None

        token = parts[1]

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token expirado.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Token inválido.")

        user_id = payload.get("sub")
        if not user_id:
            raise exceptions.AuthenticationFailed("Token inválido (sem subject).")
        
        try:
            user = Usuario.objects.get(id=user_id)
        except Usuario.DoesNotExist:
            raise exceptions.AuthenticationFailed("Usuário não encontrado.")

        return (user, None)

    def authenticate_header(self, request):

        return 'Bearer realm="api"'