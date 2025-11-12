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


class MetricasCorridaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricasCorrida
        fields = [
            "sessao",
            "distancia_km",
            "ritmo_medio_seg_km",
            "fc_media",
        ]


class MetricasCiclismoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricasCiclismo
        fields = [
            "sessao",
            "distancia_km",
            "velocidade_media_kmh",
            "fc_media",
        ]


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


class MarcacaoHabitoSerializer(serializers.ModelSerializer):
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
                {"senha_atual": "A senha atual fornecida está incorreta."}
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