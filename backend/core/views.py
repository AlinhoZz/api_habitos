from typing import Any, cast

from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.db.models import Sum, Avg, Count
from rest_framework import viewsets, filters, status, permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from datetime import datetime, timedelta
import jwt
from django.conf import settings

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
    UsuarioUpdateSerializer,
)

REFRESH_TOKEN_LIFETIME_DAYS = 7


def create_refresh_token(user: Usuario) -> str:
    now = datetime.now()
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_refresh_token(refresh_token: str) -> Usuario:
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise ValidationError("Refresh token expirado.")
    except jwt.InvalidTokenError as exc:
        raise ValidationError(f"Refresh token inválido: {exc}")

    if payload.get("type") != "refresh":
        raise ValidationError("Tipo de token inválido para refresh.")

    user_id = payload.get("sub")
    if not user_id:
        raise ValidationError("Refresh token sem usuário associado.")

    try:
        user = Usuario.objects.get(pk=int(user_id))
    except Usuario.DoesNotExist:
        raise ValidationError("Usuário não encontrado para este refresh token.")

    return user



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
        access_token = create_jwt_for_user(user)
        refresh_token = create_refresh_token(user)

        data = {
            "user": UsuarioSerializer(user).data,
            "access_token": access_token,
            "refresh_token": refresh_token,
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
        access_token = create_jwt_for_user(user)
        refresh_token = create_refresh_token(user)

        data = {
            "user": UsuarioSerializer(user).data,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        return Response(data, status=status.HTTP_200_OK)

class RefreshTokenView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            raise ValidationError({"refresh_token": "Este campo é obrigatório."})

        user = decode_refresh_token(refresh_token)

        new_access_token = create_jwt_for_user(user)

        data = {
            "access_token": new_access_token,
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
    queryset = Exercicio.objects.all().order_by("nome")
    serializer_class = ExercicioSerializer
    permission_classes = [permissions.IsAuthenticated]
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
        """
        Regra de negócio para DELETE de sessão:
        - Se a sessão tiver métricas de corrida, de ciclismo, séries de musculação
          ou marcações de hábito associadas, o DELETE é bloqueado.
        - O usuário precisa remover/ajustar esses dados antes.
        """
        instance = self.get_object()

        tem_metricas_corrida = hasattr(instance, "metricas_corrida")
        tem_metricas_ciclismo = hasattr(instance, "metricas_ciclismo")
        tem_series = instance.series_musculacao.exists()
        tem_marcacoes = instance.marcacoes.exists()

        if tem_metricas_corrida or tem_metricas_ciclismo or tem_series or tem_marcacoes:
            return Response(
                {
                    "detail": (
                        "Não é possível excluir a sessão pois existem dados associados "
                        "(métricas, séries ou marcações de hábito). "
                        "Remova ou ajuste esses dados antes de excluir a sessão."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)

        return Response(
            {"detail": "Sessão excluída com sucesso."},
            status=status.HTTP_200_OK,
        )

class MetricasCorridaViewSet(viewsets.ModelViewSet):
    queryset = MetricasCorrida.objects.select_related("sessao").all()
    serializer_class = MetricasCorridaSerializer
    
    def get_queryset(self):
        request = cast(Request, self.request)
        return (
            MetricasCorrida.objects
            .select_related("sessao")
            .filter(sessao__usuario=request.user)
        )

class MetricasCiclismoViewSet(viewsets.ModelViewSet):
    queryset = MetricasCiclismo.objects.select_related("sessao").all()
    serializer_class = MetricasCiclismoSerializer
    
    def get_queryset(self):
            request = cast(Request, self.request)
            return (
                MetricasCiclismo.objects
                .select_related("sessao")
                .filter(sessao__usuario=request.user)
            )

class SerieMusculacaoViewSet(viewsets.ModelViewSet):
    serializer_class = SerieMusculacaoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["exercicio__nome"]

    def get_queryset(self):
        request = cast(Request, self.request)

        qs = (
            SerieMusculacao.objects
            .select_related("sessao", "exercicio")
            .filter(sessao__usuario=request.user)
            .order_by("sessao_id", "ordem_serie", "id")
        )

        sessao_id = request.query_params.get("sessao_id")
        if sessao_id:
            qs = qs.filter(sessao_id=sessao_id)

        exercicio_id = request.query_params.get("exercicio_id")
        if exercicio_id:
            qs = qs.filter(exercicio_id=exercicio_id)

        return qs

    def destroy(self, request, *args, **kwargs):

        instance = self.get_object()
        sessao = instance.sessao

        response = super().destroy(request, *args, **kwargs)

        series = (
            SerieMusculacao.objects
            .filter(sessao=sessao)
            .order_by("ordem_serie", "id")
        )

        for idx, serie in enumerate(series, start=1):
            if serie.ordem_serie != idx:
                serie.ordem_serie = idx
                serie.save(update_fields=["ordem_serie"])

        return response

class MetaHabitoViewSet(viewsets.ModelViewSet):
    serializer_class = MetaHabitoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        dados_recebidos = serializer.validated_data
        
        novo_status_ativo = dados_recebidos.get('ativo')

        if novo_status_ativo is True and 'data_fim' not in dados_recebidos:
            serializer.save(usuario=self.request.user, data_fim=None)
        
        else:
            serializer.save(usuario=self.request.user)

    @action(detail=True, methods=['patch'])
    def encerrar(self, request, pk=None):
        instance = self.get_object() 
        hoje = timezone.now().date()

        instance.ativo = False

        if instance.data_inicio is None or hoje >= instance.data_inicio:
            instance.data_fim = hoje
            
        instance.save() 

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_queryset(self):
        request = cast(Request, self.request)
        qs = MetaHabito.objects.select_related("usuario").filter(usuario=request.user)

        if self.action == 'list':
            ativo_param = request.query_params.get("ativo")

            if ativo_param in {"false", "0"}:
                qs = qs.filter(ativo=False)
            else:
                qs = qs.filter(ativo=True)

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
        """
        Sempre lista só as marcações do usuário logado.
        Filtros suportados:
        - meta_id
        - data_inicio (AAAA-MM-DD)
        - data_fim (AAAA-MM-DD)
        """

        request = cast(Request, self.request)
        qs = (
        MarcacaoHabito.objects.select_related("meta", "usuario", "sessao")
        .filter(usuario=request.user)
        .order_by("data", "id")
        )

        # Filtro por meta
        meta_id = request.query_params.get("meta_id")
        if meta_id:
            qs = qs.filter(meta_id=meta_id)

        # Filtro por intervalo de datas
        data_inicio_str = request.query_params.get("data_inicio")
        data_fim_str = request.query_params.get("data_fim")

        if data_inicio_str:
            data_inicio = parse_date(data_inicio_str)
            if not data_inicio:
                raise ValidationError(
                {"data_inicio": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(data__gte=data_inicio)

        if data_fim_str:
            data_fim = parse_date(data_fim_str)
            if not data_fim:
                raise ValidationError(
                {"data_fim": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(data__lte=data_fim)


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
    
    def patch(self, request: Request) -> Response:
        user = request.user
        
        serializer = UsuarioUpdateSerializer(
            user, 
            data=request.data, 
            partial=True, 
            context={'request': request}
        )
        
        serializer.is_valid(raise_exception=True)
        updated_user = serializer.save()
        
        read_serializer = UsuarioSerializer(updated_user)
        return Response(read_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request: Request) -> Response:
        user = request.user
        
        user.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

class DashboardResumoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        try:
            dias = int(request.query_params.get("dias", 30))
            if dias < 1:
                dias = 30
        except ValueError:
            dias = 30

        data_limite = timezone.now() - timedelta(days=dias)
        qs_base = SessaoAtividade.objects.filter(usuario=request.user, inicio_em__gte=data_limite)

        geral = qs_base.aggregate(
            total_sessoes=Count("id"),
            duracao_total=Sum("duracao_seg"),
            calorias_totais=Sum("calorias")
        )

        dados_corrida = qs_base.filter(modalidade="corrida").aggregate(
            sessoes=Count("id"),
            distancia=Sum("metricas_corrida__distancia_km"),
            ritmo=Avg("metricas_corrida__ritmo_medio_seg_km")
        )

        dados_ciclismo = qs_base.filter(modalidade="ciclismo").aggregate(
            sessoes=Count("id"),
            distancia=Sum("metricas_ciclismo__distancia_km"),
            velocidade=Avg("metricas_ciclismo__velocidade_media_kmh")
        )

        dados_musculacao = qs_base.filter(modalidade="musculacao").aggregate(
            sessoes=Count("id"),
            series_totais=Count("series_musculacao__id")
        )

        response_data = {
            "periodo_dias": dias,
            "total_sessoes": geral["total_sessoes"] or 0,
            "duracao_total_segundos": geral["duracao_total"] or 0,
            "calorias_totais": geral["calorias_totais"] or 0,
            "por_modalidade": {
                "corrida": {
                    "sessoes": dados_corrida["sessoes"] or 0,
                    "distancia_total_km": dados_corrida["distancia"] or 0,
                    "ritmo_medio": dados_corrida["ritmo"] or 0,
                },
                "ciclismo": {
                    "sessoes": dados_ciclismo["sessoes"] or 0,
                    "distancia_total_km": dados_ciclismo["distancia"] or 0,
                    "velocidade_media": dados_ciclismo["velocidade"] or 0,
                },
                "musculacao": {
                    "sessoes": dados_musculacao["sessoes"] or 0,
                    "series_totais": dados_musculacao["series_totais"] or 0,
                }
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)