from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    healthz,
    UsuarioViewSet,
    ExercicioViewSet,
    SessaoAtividadeViewSet,
    MetricasCorridaViewSet,
    MetricasCiclismoViewSet,
    SerieMusculacaoViewSet,
    MetaHabitoViewSet,
    MarcacaoHabitoViewSet,
    RegisterView,
    LoginView,
    ChangePasswordView,
    MeView,
)

router = DefaultRouter()
router.register(r"usuarios", UsuarioViewSet, basename="usuario")
router.register(r"exercicios", ExercicioViewSet, basename="exercicio")
router.register(r"sessoes-atividade", SessaoAtividadeViewSet, basename="sessao-atividade")
router.register(r"metricas-corrida", MetricasCorridaViewSet, basename="metricas-corrida")
router.register(r"metricas-ciclismo", MetricasCiclismoViewSet, basename="metricas-ciclismo")
router.register(r"series-musculacao", SerieMusculacaoViewSet, basename="series-musculacao")
router.register(r"metas-habito", MetaHabitoViewSet, basename="meta-habito")
router.register(r"marcacoes-habito", MarcacaoHabitoViewSet, basename="marcacao-habito")

urlpatterns = [
    path("healthz/", healthz),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("api/", include(router.urls)),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
]
