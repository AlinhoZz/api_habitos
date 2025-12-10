from typing import Any, cast

from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.db import transaction
from django.db.models import Sum, Avg, Count, Q
from rest_framework import viewsets, filters, status, permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.throttling import UserRateThrottle

import jwt
import requests

import google.generativeai as genai
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
    ContaStrava,
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
from .strava_service import sincronizar_atividades_strava

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
        data_in = cast(dict[str, Any], request.data)
        refresh_token = data_in.get("refresh_token")

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

    def _criar_ou_atualizar_marcacoes_para_sessao(self, sessao: SessaoAtividade) -> None:
        data_sessao = sessao.inicio_em.date()

        metas = (
            MetaHabito.objects
            .filter(
                usuario=sessao.usuario,
                ativo=True,
                modalidade=sessao.modalidade,
            )
            .filter(
                Q(data_inicio__isnull=True) | Q(data_inicio__lte=data_sessao),
                Q(data_fim__isnull=True) | Q(data_fim__gte=data_sessao),
            )
        )

        for meta in metas:
            marcacao, created = MarcacaoHabito.objects.get_or_create(
                usuario=sessao.usuario,
                meta=meta,
                data=data_sessao,
                defaults={"concluido": True, "sessao": sessao},
            )
            if not created:
                if (not marcacao.concluido) or (marcacao.sessao is None):
                    marcacao.concluido = True
                    marcacao.sessao = sessao
                    marcacao.save(update_fields=["concluido", "sessao"])

    def perform_create(self, serializer):
        sessao = serializer.save(usuario=self.request.user)
        self._criar_ou_atualizar_marcacoes_para_sessao(sessao)

    def perform_update(self, serializer):
        sessao = serializer.save(usuario=self.request.user)
        self._criar_ou_atualizar_marcacoes_para_sessao(sessao)

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

        - Se a sessão tiver métricas de corrida, métricas de ciclismo
          ou séries de musculação associadas, o DELETE é bloqueado.
        - Marcações de hábito vinculadas à sessão NÃO bloqueiam o DELETE:
          elas são apagadas junto com a sessão.
        """
        instance = self.get_object()

        tem_metricas_corrida = MetricasCorrida.objects.filter(sessao=instance).exists()
        tem_metricas_ciclismo = MetricasCiclismo.objects.filter(sessao=instance).exists()
        tem_series = instance.series_musculacao.exists()

        if tem_metricas_corrida or tem_metricas_ciclismo or tem_series:
            return Response(
                {
                    "detail": (
                        "Não é possível excluir a sessão pois existem dados associados "
                        "(métricas ou séries de musculação). "
                        "Remova ou ajuste esses dados antes de excluir a sessão."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        MarcacaoHabito.objects.filter(sessao=instance).delete()

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
    
    @action(detail=True, methods=['get'])
    def historico(self, request, pk=None):
        meta = self.get_object()
        data_inicio_str = request.query_params.get('data_inicio')
        data_fim_str = request.query_params.get('data_fim')

        marcacoes = meta.marcacoes.all().order_by('data')

        if data_inicio_str:
            data_inicio = parse_date(data_inicio_str)
            if data_inicio:
                marcacoes = marcacoes.filter(data__gte=data_inicio)
        
        if data_fim_str:
            data_fim = parse_date(data_fim_str)
            if data_fim:
                marcacoes = marcacoes.filter(data__lte=data_fim)

        serializer = MarcacaoHabitoSerializer(marcacoes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def streaks(self, request, pk=None):
        meta = self.get_object()

        datas_concluidas = (
            meta.marcacoes
            .filter(concluido=True)
            .order_by('data')
            .values_list('data', flat=True)
            .distinct()
        )

        datas = sorted(list({
            (d.date() if isinstance(d, datetime) else d) 
            for d in datas_concluidas 
            if d is not None
        }))
        
        if datas:
            print(f"DEBUG STREAKS - Tipo do dado: {type(datas[0])} - Valor: {datas[0]}")

        if not datas:
            return Response({'streak_atual': 0, 'streak_maximo': 0})

        streak_maximo = 0
        current_run = 0
        ultima_data_processada = None

        for data in datas:
            if ultima_data_processada is None:
                current_run = 1
            elif data == ultima_data_processada + timedelta(days=1):
                current_run += 1
            else:
                streak_maximo = max(streak_maximo, current_run)
                current_run = 1
            
            ultima_data_processada = data
        
        streak_maximo = max(streak_maximo, current_run)

        streak_atual = 0
        hoje = timezone.now().date()
        
        if datas:
            ultima_data_registrada = datas[-1]
            
            if ultima_data_registrada == hoje or ultima_data_registrada == hoje - timedelta(days=1):
                streak_atual = 1
                for i in range(len(datas) - 2, -1, -1):
                    if datas[i+1] == datas[i] + timedelta(days=1):
                        streak_atual += 1
                    else:
                        break
        
        return Response({
            'streak_atual': streak_atual,
            'streak_maximo': streak_maximo
        })
 
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

        meta_id = request.query_params.get("meta_id")
        if meta_id:
            qs = qs.filter(meta_id=meta_id)

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
        user = request.user
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
            sessoes=Count("id", distinct=True),
            distancia=Sum("metricas_corrida__distancia_km"),
            ritmo=Avg("metricas_corrida__ritmo_medio_seg_km")
        )

        dados_ciclismo = qs_base.filter(modalidade="ciclismo").aggregate(
            sessoes=Count("id", distinct=True),
            distancia=Sum("metricas_ciclismo__distancia_km"),
            velocidade=Avg("metricas_ciclismo__velocidade_media_kmh")
        )

        dados_musculacao = qs_base.filter(modalidade="musculacao").aggregate(
            sessoes=Count("id", distinct=True),   
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
    
class StravaConnectView(APIView):
    """
    Recebe o 'code' do Strava e cria/atualiza a ContaStrava do usuário.
    POST /integracoes/strava/conectar/
    Body: { "code": "..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        data_in = cast(dict[str, Any], request.data)
        code = data_in.get("code")
        if not code:
            return Response(
                {"detail": "Código de autorização (code) é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resp = requests.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            return Response(
                {
                    "detail": "Erro de rede ao falar com a API do Strava.",
                    "error": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if resp.status_code != 200:
            return Response(
                {
                    "detail": "Erro ao trocar código por token no Strava.",
                    "raw": resp.text,
                    "status_code": resp.status_code,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = resp.json()
        except ValueError:
            return Response(
                {
                    "detail": "Resposta inesperada do Strava (não é JSON).",
                    "raw": resp.text,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        athlete = data.get("athlete")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_at_raw = data.get("expires_at")

        if not athlete or "id" not in athlete:
            return Response(
                {
                    "detail": "Resposta do Strava não contém dados de atleta.",
                    "raw": data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if access_token is None or refresh_token is None or expires_at_raw is None:
            return Response(
                {
                    "detail": "Resposta do Strava não contém tokens esperados.",
                    "raw": data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            expires_at_ts = int(expires_at_raw)
            expires_at = datetime.fromtimestamp(expires_at_ts, tz=dt_timezone.utc)

        except Exception as exc:
            return Response(
                {
                    "detail": "Não foi possível interpretar o expires_at do Strava.",
                    "expires_at_raw": expires_at_raw,
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ContaStrava.objects.update_or_create(
                usuario=request.user,
                defaults={
                    "athlete_id": athlete["id"],
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_expires_at": expires_at,
                },
            )
        except Exception as exc:
            return Response(
                {
                    "detail": "Erro ao salvar dados da conta Strava no banco.",
                    "error": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "Conta Strava conectada com sucesso."},
            status=status.HTTP_200_OK,
        )


class StravaSyncView(APIView):
    """
    Sincroniza atividades do Strava para o usuário logado.
    POST /integracoes/strava/sync/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        try:
            conta = request.user.conta_strava
        except ContaStrava.DoesNotExist:
            return Response(
                {"detail": "Você ainda não conectou sua conta Strava."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qtd = sincronizar_atividades_strava(conta)
        return Response(
            {"detail": f"{qtd} atividades importadas do Strava."},
            status=status.HTTP_200_OK,
        )
        return Response(response_data, status=status.HTTP_200_OK)
class AIChatThrottle(UserRateThrottle):
    scope = 'ai_chat'

    def allow_request(self, request, view):
        is_allowed = super().allow_request(request, view)
        
        ident = self.get_cache_key(request, view)
        
        print(f"DEBUG THROTTLE: User={request.user} | Key={ident} | Permitido? {is_allowed}")
        
        return is_allowed

class FitnessAIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    throttle_classes = [AIChatThrottle]

    def post(self, request: Request) -> Response:
        pergunta = request.data.get("pergunta")
        nome_exercicio = request.data.get("nome_exercicio")
        contexto_exercicio = request.data.get("contexto_exercicio", "")
        eh_primeira_msg = request.data.get("primeira_mensagem", False)
        historico = request.data.get("historico", [])
        
        nome_usuario = getattr(request.user, 'nome', 'Atleta')

        if not pergunta or not nome_exercicio:
            return Response(
                {"erro": "Os campos 'pergunta' e 'nome_exercicio' são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not settings.GEMINI_API_KEY:
            return Response(
                {"erro": "Chave de API do Gemini não configurada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)

            system_instruction = f"""
            Você é o O2, um treinador pessoal parceiro, experiente e especialista em biomecânica do app '+Fôlego'.
            
            CONTEXTO ATUAL:
            Aluno: {nome_usuario}
            Exercício: {nome_exercicio}
            Ficha Técnica: {contexto_exercicio}

            REGRAS DE SEGURANÇA:
            1. VOCÊ NÃO É MÉDICO;
            2. Responda em português do Brasil;
            3. Não perca o foco do assunto.

            DIRETRIZES DE PERSONALIDADE (IMPORTANTE):
            1. TOM DE VOZ: Natural, humano e direto. Imagine que você está falando pelo WhatsApp. Evite formalidades robóticas.
            2. FORMATAÇÃO: EVITE LISTAS e TÓPICOS (bullet points) a todo custo, a menos que seja um passo-a-passo estrito. Prefira parágrafos curtos e fluidos.
            3. POSTURA: Seja motivador, mas responsável. Se o aluno relatar dor aguda, dê o alerta de segurança imediatamente, mas com acolhimento (sem parecer uma bula de remédio).
            4. FOCO: Responda a dúvida de forma objetiva. Não dê palestras longas se a pergunta for simples.
            """

            model = genai.GenerativeModel(
                'models/gemini-2.5-flash',
                system_instruction=system_instruction
            )

            gemini_history = []
            for msg in historico:
                role = "user" if msg.get('role') == 'user' else "model"
                
                content = msg.get('content', '').replace("⚠️ ", "")
                
                gemini_history.append({
                    "role": role,
                    "parts": [content]
                })

            chat = model.start_chat(history=gemini_history)

            msg_atual = pergunta
            
            if eh_primeira_msg:
                msg_atual = f"[Instrução de sistema: Comece a resposta saudando o {nome_usuario} de forma breve e animada como o O2]. " + pergunta

            response = chat.send_message(msg_atual)
            
            return Response({"resposta": response.text}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Erro no Gemini: {e}")
            return Response(
                {"erro": f"Erro ao processar inteligência: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
