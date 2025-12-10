import requests
from datetime import datetime
from django.utils import timezone
from django.conf import settings

from .models import (
    ContaStrava,
    SessaoAtividade,
    MetricasCorrida,
    MetricasCiclismo,
    ModalidadeChoices,
)

STRAVA_BASE_URL = "https://www.strava.com/api/v3"

# Esses valores você coloca no settings.py / .env
STRAVA_CLIENT_ID = settings.STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET = settings.STRAVA_CLIENT_SECRET


def _refresh_strava_token(conta: ContaStrava) -> str:
    """
    Garante que o access_token está válido.
    Se estiver expirado, usa o refresh_token.
    """
    if conta.token_expires_at > timezone.now():
        return conta.access_token

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": conta.refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    conta.access_token = data["access_token"]
    conta.refresh_token = data["refresh_token"]
    conta.token_expires_at = datetime.fromtimestamp(
        data["expires_at"], tz=timezone.utc
    )
    conta.save(update_fields=["access_token", "refresh_token", "token_expires_at"])
    return conta.access_token


def _map_modalidade(activity: dict) -> str | None:
    sport_type = activity.get("sport_type") or activity.get("type")
    if sport_type in ["Run", "TrailRun"]:
        return ModalidadeChoices.CORRIDA
    if sport_type in ["Ride", "VirtualRide", "GravelRide"]:
        return ModalidadeChoices.CICLISMO
    return None


def sincronizar_atividades_strava(conta: ContaStrava, per_page: int = 50) -> int:
    """
    Busca atividades do Strava e cria SessaoAtividade + métricas
    somente com os campos que o +Fôlego já usa.
    """
    access_token = _refresh_strava_token(conta)

    params = {
        "per_page": per_page,
        "page": 1,
    }

    importadas = 0

    while True:
        resp = requests.get(
            f"{STRAVA_BASE_URL}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        atividades = resp.json()
        if not atividades:
            break

        for a in atividades:
            modalidade = _map_modalidade(a)
            if not modalidade:
                continue  # ignora esportes que não usamos

            strava_id = a["id"]
            if SessaoAtividade.objects.filter(strava_activity_id=strava_id).exists():
                continue  # já importou essa

            # --- Sessão base ---
            start_local = a["start_date_local"]  # ex: "2025-11-30T10:15:30Z"
            inicio_em = datetime.fromisoformat(start_local.replace("Z", "+00:00"))

            duracao_seg = a.get("moving_time")
            calorias = a.get("calories", None)

            sessao = SessaoAtividade.objects.create(
                usuario=conta.usuario,
                modalidade=modalidade,
                inicio_em=inicio_em,
                duracao_seg=duracao_seg,
                calorias=calorias,
                observacoes="Importado do Strava",
                origem="strava",
                strava_activity_id=strava_id,
            )

            # --- Métricas específicas ---
            distance_m = a.get("distance") or 0
            distancia_km = round(distance_m / 1000.0, 2) if distance_m else 0
            avg_hr = a.get("average_heartrate")

            if modalidade == ModalidadeChoices.CORRIDA and distancia_km > 0:
                ritmo_medio = int(duracao_seg / distancia_km) if duracao_seg else 0

                MetricasCorrida.objects.create(
                    sessao=sessao,
                    distancia_km=distancia_km,
                    ritmo_medio_seg_km=ritmo_medio,
                    fc_media=avg_hr,
                )

            if modalidade == ModalidadeChoices.CICLISMO and duracao_seg and duracao_seg > 0:
                velocidade_media_kmh = (
                    distancia_km / (duracao_seg / 3600.0)
                    if distancia_km > 0 else 0
                )

                MetricasCiclismo.objects.create(
                    sessao=sessao,
                    distancia_km=distancia_km,
                    velocidade_media_kmh=velocidade_media_kmh,
                    fc_media=avg_hr,
                )

            importadas += 1

        params["page"] += 1

    conta.last_sync = timezone.now()
    conta.save(update_fields=["last_sync"])
    return importadas
