from django.db import models

# Create your models here.
from django.db import models


class Usuario(models.Model):
    """
    Representa um usuário da aplicação.
    Tabela: usuarios
    """
    id = models.BigAutoField(primary_key=True)
    nome = models.CharField(max_length=120)
    email = models.EmailField(max_length=254, unique=True)
    hash_senha = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "usuarios"

    def __str__(self) -> str:
        return self.nome


class Exercicio(models.Model):
    """
    Catálogo de exercícios.
    Tabela: exercicios
    """
    id = models.BigAutoField(primary_key=True)
    nome = models.CharField(max_length=120)
    grupo_muscular = models.CharField(max_length=60, blank=True, null=True)
    equipamento = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "exercicios"

    def __str__(self) -> str:
        return self.nome


class ModalidadeChoices(models.TextChoices):
    CORRIDA = "corrida", "Corrida"
    CICLISMO = "ciclismo", "Ciclismo"
    MUSCULACAO = "musculacao", "Musculação"


class SessaoAtividade(models.Model):
    """
    Sessões de atividade física.
    Tabela: sessoes_atividade
    """
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column="usuario_id",
        related_name="sessoes",
    )
    modalidade = models.CharField(
        max_length=20,
        choices=ModalidadeChoices.choices,
    )
    inicio_em = models.DateTimeField()
    duracao_seg = models.IntegerField(blank=True, null=True)
    calorias = models.IntegerField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "sessoes_atividade"
        indexes = [
            models.Index(
                fields=["usuario", "-inicio_em"],
                name="idx_sessoes_usuario_tempo",
            ),
            models.Index(
                fields=["modalidade"],
                name="idx_sessoes_modalidade",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} - {self.modalidade} em {self.inicio_em:%Y-%m-%d}"


class MetricasCorrida(models.Model):
    """
    Métricas adicionais para sessões de corrida.
    Tabela: metricas_corrida
    """
    sessao = models.OneToOneField(
        SessaoAtividade,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="sessao_id",
        related_name="metricas_corrida",
    )
    distancia_km = models.DecimalField(max_digits=7, decimal_places=2)
    ritmo_medio_seg_km = models.IntegerField()
    fc_media = models.SmallIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "metricas_corrida"

    def __str__(self) -> str:
        return f"Corrida {self.sessao.pk}"


class MetricasCiclismo(models.Model):
    """
    Métricas adicionais para sessões de ciclismo.
    Tabela: metricas_ciclismo
    """
    sessao = models.OneToOneField(
        SessaoAtividade,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="sessao_id",
        related_name="metricas_ciclismo",
    )
    distancia_km = models.DecimalField(max_digits=7, decimal_places=2)
    velocidade_media_kmh = models.DecimalField(max_digits=5, decimal_places=2)
    fc_media = models.SmallIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "metricas_ciclismo"

    def __str__(self) -> str:
        return f"Ciclismo {self.sessao.pk}"


class SerieMusculacao(models.Model):
    """
    Séries de musculação.
    Tabela: series_musculacao
    """
    id = models.BigAutoField(primary_key=True)
    sessao = models.ForeignKey(
        SessaoAtividade,
        on_delete=models.CASCADE,
        db_column="sessao_id",
        related_name="series_musculacao",
    )
    exercicio = models.ForeignKey(
        Exercicio,
        on_delete=models.PROTECT,
        db_column="exercicio_id",
        related_name="series",
    )
    ordem_serie = models.IntegerField()
    repeticoes = models.IntegerField(blank=True, null=True)
    carga_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )

    class Meta:
        managed = False
        db_table = "series_musculacao"
        indexes = [
            models.Index(
                fields=["sessao"],
                name="idx_series_sessao",
            ),
            models.Index(
                fields=["exercicio"],
                name="idx_series_exercicio",
            ),
        ]

    def __str__(self) -> str:
        return f"Sessão {self.sessao.pk} - Série {self.ordem_serie}"


class MetaHabito(models.Model):
    """
    Metas de hábito do usuário.
    Tabela: metas_habito
    """
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column="usuario_id",
        related_name="metas",
    )
    titulo = models.CharField(max_length=120)
    modalidade = models.CharField(
        max_length=20,
        choices=ModalidadeChoices.choices,
    )
    data_inicio = models.DateField()
    data_fim = models.DateField(blank=True, null=True)
    frequencia_semana = models.SmallIntegerField(blank=True, null=True)
    distancia_meta_km = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True,
    )
    duracao_meta_min = models.IntegerField(blank=True, null=True)
    sessoes_meta = models.IntegerField(blank=True, null=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "metas_habito"

    def __str__(self) -> str:
        return f"{self.titulo} ({self.usuario})"


class MarcacaoHabito(models.Model):
    """
    Marcações diárias de metas de hábito.
    Tabela: marcacoes_habito
    """
    id = models.BigAutoField(primary_key=True)
    meta = models.ForeignKey(
        MetaHabito,
        on_delete=models.CASCADE,
        db_column="meta_id",
        related_name="marcacoes",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column="usuario_id",
        related_name="marcacoes",
    )
    data = models.DateField()
    sessao = models.ForeignKey(
        SessaoAtividade,
        on_delete=models.SET_NULL,
        db_column="sessao_id",
        related_name="marcacoes",
        blank=True,
        null=True,
    )
    concluido = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "marcacoes_habito"
        unique_together = ("meta", "data")

    def __str__(self) -> str:
        return f"{self.meta} em {self.data}"
