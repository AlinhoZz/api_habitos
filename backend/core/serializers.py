from django.contrib.auth.hashers import make_password, check_password
from rest_framework import serializers

from .models import (
    Usuario,
    Exercicio,
    SessaoAtividade,
    MetricasCorrida,
    MetricasCiclismo,
    SerieMusculacao,
    MetaHabito,
    MarcacaoHabito,
    ModalidadeChoices,
)


# ---------- SERIALIZERS DE MODELOS ----------


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nome", "email", "criado_em"]


class ExercicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercicio
        fields = ["id", "nome", "grupo_muscular", "equipamento"]

# =================== Danilo e Alisson =====================

class SessaoAtividadeSerializer(serializers.ModelSerializer):
    usuario = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = SessaoAtividade
        fields = [
            "id",
            "usuario",
            "modalidade",
            "inicio_em",
            "duracao_seg",
            "calorias",
            "observacoes",
            "criado_em",
        ]
    def validate_duracao_seg(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("A duração não pode ser negativa.")
        return value

    def validate_calorias(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("As calorias não podem ser negativas.")
        return value


class MetricasCorridaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricasCorrida
        fields = [
            "sessao",
            "distancia_km",
            "ritmo_medio_seg_km",
            "fc_media",
        ]

    def validate_sessao(self, sessao):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            return sessao

        if sessao.usuario != user:
            raise serializers.ValidationError(
                "Você não pode registrar métricas para sessões de outro usuário."
            )

        if sessao.modalidade != ModalidadeChoices.CORRIDA:
            raise serializers.ValidationError(
                "A sessão associada deve ser de modalidade corrida."
            )

        return sessao

    
class MetricasCiclismoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricasCiclismo
        fields = [
            "sessao",
            "distancia_km",
            "velocidade_media_kmh",
            "fc_media",
        ]

    def validate_sessao(self, sessao):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            return sessao

        if sessao.usuario != user:
            raise serializers.ValidationError(
                "Você não pode registrar métricas para sessões de outro usuário."
            )

        if sessao.modalidade != ModalidadeChoices.CICLISMO:
            raise serializers.ValidationError(
                "A sessão associada deve ser de modalidade ciclismo."
            )

        return sessao

class SerieMusculacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SerieMusculacao
        fields = [
            "id",
            "sessao",
            "exercicio",
            "ordem_serie",
            "repeticoes",
            "carga_kg",
        ]
    def validate_sessao(self, sessao):

        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            return sessao

        if sessao.usuario_id != user.id:
            raise serializers.ValidationError(
                "Você não pode criar séries em sessões de outro usuário."
            )

        if sessao.modalidade != ModalidadeChoices.MUSCULACAO:
            raise serializers.ValidationError(
                "A sessão associada deve ser de modalidade musculação."
            )

        return sessao

    def validate(self, attrs):
        instance = self.instance

        sessao = attrs.get("sessao") or getattr(instance, "sessao", None)
        ordem_serie = attrs.get("ordem_serie") or getattr(instance, "ordem_serie", None)

        if sessao is None or ordem_serie is None:
            return attrs

        if ordem_serie < 1:
            raise serializers.ValidationError(
                {"ordem_serie": "A ordem da série deve ser um número inteiro maior ou igual a 1."}
            )

        qs = SerieMusculacao.objects.filter(
            sessao=sessao,
            ordem_serie=ordem_serie,
        )

        if instance is not None:
            qs = qs.exclude(pk=instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                {"ordem_serie": "Já existe uma série com essa ordem nessa sessão."}
            )

        return attrs

    def create(self, validated_data):
        if "ordem_serie" not in validated_data or validated_data["ordem_serie"] is None:
            sessao = validated_data["sessao"]
            ultima = (
                SerieMusculacao.objects
                .filter(sessao=sessao)
                .order_by("-ordem_serie")
                .first()
            )
            proxima_ordem = (ultima.ordem_serie if ultima else 0) + 1
            validated_data["ordem_serie"] = proxima_ordem

        return super().create(validated_data)
    
# =================== Meta Hábito =======================
class MetaHabitoSerializer(serializers.ModelSerializer):
    usuario = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = MetaHabito
        fields = [
            "id",
            "usuario",
            "titulo",
            "modalidade",
            "data_inicio",
            "data_fim",
            "frequencia_semana",
            "distancia_meta_km",
            "duracao_meta_min",
            "sessoes_meta",
            "ativo",
            "criado_em",
        ]

    def validate(self, data):
        is_update = self.instance is not None
        
        data_inicio = data.get('data_inicio', self.instance.data_inicio if is_update else None) 
        data_fim = data.get('data_fim', self.instance.data_fim if is_update else None) 
        
        if data_inicio and data_fim and data_fim < data_inicio:
            raise serializers.ValidationError(
                {"data_fim": "A data final do hábito não pode ser anterior à data de início."}
            )
        
        frequencia = data.get('frequencia_semana', self.instance.frequencia_semana if is_update else None)
        distancia = data.get('distancia_meta_km', self.instance.distancia_meta_km if is_update else None)
        duracao = data.get('duracao_meta_min', self.instance.duracao_meta_min if is_update else None)
        sessoes = data.get('sessoes_meta', self.instance.sessoes_meta if is_update else None)

        if (frequencia is None and 
            distancia is None and 
            duracao is None and 
            sessoes is None):
            
            raise serializers.ValidationError(
                "A meta de hábito deve ter pelo menos um 'alvo' definido (frequência, distância, duração ou sessões)."
            )
            
        return data    
# =================== Carlos e Abelardo =====================

class MarcacaoHabitoSerializer(serializers.ModelSerializer):
    # Usuario sempre vem do request, nunca do body
    usuario = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = MarcacaoHabito
        fields = [
            "id",
            "meta",
            "usuario",
            "data",
            "sessao",
            "concluido",
            "criado_em",
        ]

    def validate(self, attrs):
        
        request = self.context.get("request")
        user = getattr(request, "user", None)

        meta = attrs.get("meta") or getattr(self.instance, "meta", None)
        data = attrs.get("data") or getattr(self.instance, "data", None)
        sessao = attrs.get("sessao") or getattr(self.instance, "sessao", None)

        if not user or not meta or not data:
            return attrs

        # 1) Meta precisa ser do usuário logado
        if meta.usuario_id != user.id:
            raise serializers.ValidationError(
                {"meta": "Você só pode marcar dias de metas que são suas."}
            )

        # 2) Se houver sessão, também precisa ser do usuário logado
        if sessao and sessao.usuario_id != user.id:
            raise serializers.ValidationError(
                {"sessao": "Você só pode vincular sessões que são suas."}
            )

        # 3) Respeitar unique_together (meta, data)
        qs = MarcacaoHabito.objects.filter(meta=meta, data=data)

        # Se for update, ignora a própria instância
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                {"data": "Já existe uma marcação para essa meta nesse dia."}
            )

        return attrs

# ---------- SERIALIZERS DE AUTENTICAÇÃO ----------


class RegisterSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    senha = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        if Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Já existe um usuário com este e-mail.")
        return value

    def create(self, validated_data):
        senha = validated_data.pop("senha")
        user = Usuario(
            nome=validated_data["nome"],
            email=validated_data["email"],
            hash_senha=make_password(senha),
        )
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    senha = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        senha = attrs.get("senha")

        try:
            user = Usuario.objects.get(email__iexact=email)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError("Credenciais inválidas.")

        if not check_password(senha, user.hash_senha):
            raise serializers.ValidationError("Credenciais inválidas.")

        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer para a troca de senha do usuário autenticado."""

    senha_atual = serializers.CharField(required=True, write_only=True)
    nova_senha = serializers.CharField(required=True, write_only=True, min_length=6)
    nova_senha_confirmacao = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        user = self.context['request'].user
        
        if not check_password(data.get('senha_atual'), user.hash_senha):
            raise serializers.ValidationError(
                "A senha atual fornecida está incorreta. Não foi possível alterar a senha."
            )
            
        if data.get('senha_atual') == data.get('nova_senha'):
            raise serializers.ValidationError(
                {"nova_senha": "A nova senha não pode ser igual à senha atual."}
            )    
        
        if data.get('nova_senha') != data.get('nova_senha_confirmacao'):
            raise serializers.ValidationError(
                {"nova_senha_confirmacao": "As novas senhas não coincidem."}
            )

        return data
    
    def save(self):
        user = self.context['request'].user
        assert isinstance(self.validated_data, dict)
        nova_senha = self.validated_data['nova_senha']
        
        # Usa make_password para gerar o hash seguro da nova senha
        user.hash_senha = make_password(nova_senha)
        user.save()
        
        return user
    
class UsuarioUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False)
    nome = serializers.CharField(max_length=120, required=False)

    class Meta:
        model = Usuario
        fields = ["nome", "email"]

    def validate_email(self, value):
        user = self.context['request'].user
        
        email_normalizado = value.lower()

        query = Usuario.objects.filter(email__iexact=email_normalizado).exclude(pk=user.pk)

        if query.exists():
            raise serializers.ValidationError("Este e-mail já está em uso por outro usuário.")
        
        return email_normalizado

    def update(self, instance, validated_data):
        instance.nome = validated_data.get('nome', instance.nome)
        instance.email = validated_data.get('email', instance.email)
        instance.save()
        return instance    