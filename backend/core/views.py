from typing import Any, cast

from django.http import JsonResponse
from django.utils.dateparse import parse_date
from rest_framework import viewsets, filters, status, permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated


from .authentication import create_jwt_for_user
from .models import (
    Usuario,
    Exercicio,
    SessaoAtividade,
    MetricasCorrida,
    MetricasCiclismo,
    SerieMusculacao,
    MetaHabito,
    MarcacaoHabito,
)
from .serializers import (
    UsuarioSerializer,
    ChangePasswordSerializer,
    ExercicioSerializer,
    SessaoAtividadeSerializer,
    MetricasCorridaSerializer,
    MetricasCiclismoSerializer,
    SerieMusculacaoSerializer,
    MetaHabitoSerializer,
    MarcacaoHabitoSerializer,
    RegisterSerializer,
    LoginSerializer,
)


def healthz(request):
    """
    Endpoint simples de health check.
    Continua funcionando em /healthz/.
    """
    return JsonResponse({"status": "ok"})

class RegisterView(APIView):
    """
    Registro de novo usuário.
    POST /auth/register/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = cast(Usuario, serializer.save())
        token = create_jwt_for_user(user)

        data = {
            "user": UsuarioSerializer(user).data,
            "access_token": token,
        }
        return Response(data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    Login de usuário existente.
    POST /auth/login/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated: dict[str, Any] = cast(dict[str, Any], serializer.validated_data)

        user_obj = validated.get("user")
        if not isinstance(user_obj, Usuario):
            raise ValidationError("Credenciais inválidas.")

        user: Usuario = user_obj
        token = create_jwt_for_user(user)

        data = {
            "user": UsuarioSerializer(user).data,
            "access_token": token,
        }
        return Response(data, status=status.HTTP_200_OK)

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    
    def patch(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            response_data = {
                "detail": "Senha alterada com sucesso",
            }
            return Response(response_data, status=status.HTTP_200_OK)

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["nome", "email"]


class ExercicioViewSet(viewsets.ModelViewSet):
    queryset = Exercicio.objects.all().order_by("id")
    serializer_class = ExercicioSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["nome", "grupo_muscular", "equipamento"]


class SessaoAtividadeViewSet(viewsets.ModelViewSet):
    serializer_class = SessaoAtividadeSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["modalidade", "observacoes"]

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)
         
    def perform_update(self, serializer):
        serializer.save(usuario=self.request.user)
        
    def get_queryset(self):
        request = cast(Request, self.request)

        qs = (
            SessaoAtividade.objects.select_related("usuario")
            .filter(usuario=request.user)
            .order_by("-inicio_em")
        )

        modalidade = request.query_params.get("modalidade")
        if modalidade:
            qs = qs.filter(modalidade=modalidade)

        data_inicio_str = request.query_params.get("inicio_em_inicio")
        data_fim_str = request.query_params.get("inicio_em_fim")

        if data_inicio_str:
            data_inicio = parse_date(data_inicio_str)
            if not data_inicio:
                raise ValidationError(
                    {"inicio_em_inicio": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(inicio_em__date__gte=data_inicio)

        if data_fim_str:
            data_fim = parse_date(data_fim_str)
            if not data_fim:
                raise ValidationError(
                    {"inicio_em_fim": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(inicio_em__date__lte=data_fim)

        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response(
            {"detail": "Sessão excluída com sucesso."},
            status=status.HTTP_200_OK,
        )

class MetricasCorridaViewSet(viewsets.ModelViewSet):
    queryset = MetricasCorrida.objects.select_related("sessao").all()
    serializer_class = MetricasCorridaSerializer


class MetricasCiclismoViewSet(viewsets.ModelViewSet):
    queryset = MetricasCiclismo.objects.select_related("sessao").all()
    serializer_class = MetricasCiclismoSerializer


class SerieMusculacaoViewSet(viewsets.ModelViewSet):
    queryset = SerieMusculacao.objects.select_related("sessao", "exercicio").all()
    serializer_class = SerieMusculacaoSerializer


class MetaHabitoViewSet(viewsets.ModelViewSet):
    serializer_class = MetaHabitoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        serializer.save(usuario=self.request.user)

    def get_queryset(self):
        request = cast(Request, self.request)

        qs = (
            MetaHabito.objects.select_related("usuario")
            .filter(usuario=request.user)
        )
        
        ativo_param = request.query_params.get("ativo")
        if ativo_param in {"true", "false", "1", "0"}:
            ativo = ativo_param.lower() in {"true", "1"}
            qs = qs.filter(ativo=ativo)

        return qs
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.marcacoes.exists():
            instance.ativo = False
            instance.save()
            message = "Meta encerrada (desativada), pois já possui um histórico de marcações."
        else:
            instance.delete()
            message = "Meta permanentemente excluída, pois não possuía histórico."

        return Response({"detail": message}, status=status.HTTP_200_OK)


class MarcacaoHabitoViewSet(viewsets.ModelViewSet):
    serializer_class = MarcacaoHabitoSerializer

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        serializer.save(usuario=self.request.user)

    def get_queryset(self):
        request = cast(Request, self.request)
            
        qs = MarcacaoHabito.objects.select_related(
            "meta",
            "usuario",
            "sessao",
        ).filter(usuario=request.user)

        meta_id = request.query_params.get("meta_id")
        if meta_id:
            qs = qs.filter(meta_id=meta_id)

        return qs

class MeView(APIView):
    """
    Retorna os dados do usuário autenticado.
    GET /auth/me/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user  # vem do JWTAuthentication
        serializer = UsuarioSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)