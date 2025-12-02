from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth.hashers import make_password, check_password
from .models import Usuario
from datetime import date, timedelta
from .models import MetaHabito, MarcacaoHabito
from .models import SessaoAtividade
from django.utils import timezone
from .models import MetricasCorrida
from .models import Exercicio, SerieMusculacao

class UserAccountTests(APITestCase):

    def setUp(self):
        self.senha_plana = 'senha_antiga_123'

        self.user = Usuario.objects.create(
            nome='Usuario Teste',
            email='teste@exemplo.com',
            hash_senha=make_password(self.senha_plana) 
        )

        self.url_me = reverse('auth-me') 
        self.url_change_password = reverse('change-password') 

    def test_atualizar_perfil_com_sucesso(self):

        self.client.force_authenticate(user=self.user)

        payload = {
            'nome': 'Nome Atualizado',
            'email': 'novo@email.com'
        }

        response = self.client.patch(self.url_me, payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.nome, 'Nome Atualizado')
        self.assertEqual(self.user.email, 'novo@email.com')

    def test_nao_deve_atualizar_email_duplicado(self):
        Usuario.objects.create(
            nome='Outro', 
            email='ocupado@email.com', 
            hash_senha='xyz'
        )
        
        self.client.force_authenticate(user=self.user)
        payload = {'email': 'ocupado@email.com'}
        
        response = self.client.patch(self.url_me, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trocar_senha_sucesso(self):
        
        self.client.force_authenticate(user=self.user)
        
        nova_senha = 'nova_senha_forte_456'
        
        payload = {
            'senha_atual': self.senha_plana,          
            'nova_senha': nova_senha,                
            'nova_senha_confirmacao': nova_senha     
        }
        
        response = self.client.patch(self.url_change_password, payload)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], "Senha alterada com sucesso")
        self.user.refresh_from_db()
        self.assertTrue(check_password(nova_senha, self.user.hash_senha))

    def test_trocar_senha_falha_confirmacao_diferente(self):
        
        self.client.force_authenticate(user=self.user)
        
        payload = {
            'senha_atual': self.senha_plana,
            'nova_senha': 'senha_A',
            'nova_senha_confirmacao': 'senha_B' 
        }
        
        response = self.client.patch(self.url_change_password, payload)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nova_senha_confirmacao', response.data)

    def test_trocar_senha_falha_senha_atual_errada(self):
        
        self.client.force_authenticate(user=self.user)
        
        payload = {
            'senha_atual': 'senha_errada_totalmente',
            'nova_senha': 'nova',
            'nova_senha_confirmacao': 'nova'
        }
        
        response = self.client.patch(self.url_change_password, payload)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class MetaHabitoTests(APITestCase):

    def test_editar_meta(self):
        meta = MetaHabito.objects.create(
            usuario=self.user,
            titulo="Título Velho",
            modalidade="corrida",
            data_inicio=date.today(),
            frequencia_semana=3
        )
        
        url_detalhe = reverse('meta-habito-detail', kwargs={'pk': meta.pk})
        payload = {"titulo": "Título Novo"}
        
        response = self.client.patch(url_detalhe, payload)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MetaHabito.objects.get(pk=meta.pk).titulo, "Título Novo")

    def test_deletar_meta(self):
        meta = MetaHabito.objects.create(
            usuario=self.user,
            titulo="Meta Temporária",
            modalidade="ciclismo",
            data_inicio=date.today()
        )
        
        url_detalhe = reverse('meta-habito-detail', kwargs={'pk': meta.pk})
        
        response = self.client.delete(url_detalhe)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK) 
        self.assertFalse(MetaHabito.objects.filter(pk=meta.pk).exists())

    def test_impedir_acesso_meta_outro_usuario(self):
        outro_user = Usuario.objects.create(nome='Outro', email='outro@teste.com', hash_senha='123')
        meta_do_outro = MetaHabito.objects.create(
            usuario=outro_user,
            titulo="Meta Dele",
            modalidade="corrida",
            data_inicio=date.today()
        )
        
        url_detalhe = reverse('meta-habito-detail', kwargs={'pk': meta_do_outro.pk})
        
        response = self.client.delete(url_detalhe)

        self.assertTrue(response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def setUp(self):
        self.user = Usuario.objects.create(
            nome='Atleta Teste',
            email='atleta@teste.com',
            hash_senha=make_password('senha123')
        )
        self.client.force_authenticate(user=self.user)
        self.url_meta_list = reverse('meta-habito-list') 
        self.url_marcacao_list = reverse('marcacao-habito-list')

    def test_criar_meta_com_sucesso(self):
        payload = {
            "titulo": "Correr Todo Dia",
            "modalidade": "corrida",
            "data_inicio": str(date.today()),
            "frequencia_semana": 5 
        }

        response = self.client.post(self.url_meta_list, payload)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MetaHabito.objects.count(), 1)
        self.assertEqual(MetaHabito.objects.get().titulo, "Correr Todo Dia")

    def test_bloquear_data_fim_invalida(self):
        hoje = date.today()
        ontem = hoje - timedelta(days=1)

        payload = {
            "titulo": "Meta Impossível",
            "modalidade": "ciclismo",
            "data_inicio": str(hoje),
            "data_fim": str(ontem),
            "frequencia_semana": 3
        }

        response = self.client.post(self.url_meta_list, payload)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('data_fim', response.data)

    def test_marcar_habito_concluido(self):
        meta = MetaHabito.objects.create(
            usuario=self.user,
            titulo="Musculação",
            modalidade="musculacao",
            data_inicio=date.today(),
            frequencia_semana=3
        )

        payload = {
            "meta": meta.id,
            "data": str(date.today())
        }

        response = self.client.post(self.url_marcacao_list, payload)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MarcacaoHabito.objects.count(), 1)

    def test_nao_pode_marcar_habito_duplicado(self):
        meta = MetaHabito.objects.create(
            usuario=self.user,
            titulo="Natação",
            modalidade="natacao",
            data_inicio=date.today(),
            frequencia_semana=3
        )

        MarcacaoHabito.objects.create(meta=meta, usuario=self.user, data=date.today())

        payload = {
            "meta": meta.id,
            "data": str(date.today())
        }
        response = self.client.post(self.url_marcacao_list, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)        

class SessaoAtividadeTests(APITestCase):

    def test_listar_apenas_sessoes_proprias(self):
        SessaoAtividade.objects.create(usuario=self.user, modalidade="corrida", inicio_em=timezone.now())

        outro = Usuario.objects.create(nome='Vizinho', email='vizinho@t.com', hash_senha='123')
        SessaoAtividade.objects.create(usuario=outro, modalidade="ciclismo", inicio_em=timezone.now())

        response = self.client.get(self.url_sessao)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['modalidade'], 'corrida')

    def test_bloquear_delete_sessao_com_dados_vinculados(self):
        sessao = SessaoAtividade.objects.create(
            usuario=self.user, 
            modalidade="corrida", 
            inicio_em=timezone.now()
        )
        MetricasCorrida.objects.create(
            sessao=sessao, 
            distancia_km=10, 
            ritmo_medio_seg_km=300
        )

        url_detalhe = reverse('sessao-atividade-detail', kwargs={'pk': sessao.pk})
        
        response = self.client.delete(url_detalhe)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(SessaoAtividade.objects.filter(pk=sessao.pk).exists())

    def setUp(self):
        self.user = Usuario.objects.create(
            nome='Maratonista',
            email='run@teste.com',
            hash_senha=make_password('senha123')
        )
        self.client.force_authenticate(user=self.user)
        self.url_sessao = reverse('sessao-atividade-list')

    def test_registrar_treino_simples(self):
        payload = {
            "modalidade": "corrida",
            "inicio_em": str(timezone.now()),
            "duracao_seg": 3600, # 1 hora
            "calorias": 500,
            "observacoes": "Treino leve no parque"
        }

        response = self.client.post(self.url_sessao, payload)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SessaoAtividade.objects.count(), 1)
        self.assertEqual(SessaoAtividade.objects.get().modalidade, "corrida")

    def test_validar_duracao_negativa(self):
        payload = {
            "modalidade": "musculacao",
            "inicio_em": str(timezone.now()),
            "duracao_seg": -100,
            "calorias": -50  
        }

        response = self.client.post(self.url_sessao, payload)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('duracao_seg', response.data)
        self.assertIn('calorias', response.data)

    def test_automacao_marcar_habito_ao_criar_sessao(self):
        
        meta = MetaHabito.objects.create(
            usuario=self.user,
            titulo="Pedalar Todo Dia",
            modalidade="ciclismo",
            data_inicio=date.today(),
            ativo=True
        )

        self.assertEqual(MarcacaoHabito.objects.count(), 0)

        payload = {
            "modalidade": "ciclismo",
            "inicio_em": str(timezone.now()),
        }

        response = self.client.post(self.url_sessao, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(MarcacaoHabito.objects.count(), 1)
        
        marcacao = MarcacaoHabito.objects.first()
        self.assertEqual(marcacao.meta, meta)
        self.assertTrue(marcacao.concluido)
        self.assertEqual(marcacao.sessao.id, response.data['id'])

    def test_nao_deve_marcar_habito_de_modalidade_diferente(self):
        
        MetaHabito.objects.create(
            usuario=self.user,
            titulo="Correr",
            modalidade="corrida",
            data_inicio=date.today()
        )

        payload = {
            "modalidade": "musculacao",
            "inicio_em": str(timezone.now()),
            "duracao_seg": 3000
        }

        self.client.post(self.url_sessao, payload)

        self.assertEqual(MarcacaoHabito.objects.count(), 0)  

class DashboardTests(APITestCase):

    def setUp(self):
        self.user = Usuario.objects.create(
            nome='Analista de Dados', 
            email='data@teste.com', 
            hash_senha=make_password('123')
        )
        self.client.force_authenticate(user=self.user)
        self.url_dashboard = reverse('dashboard-resumo')

    def test_dashboard_calcula_totais_corretamente(self):
        sessao1 = SessaoAtividade.objects.create(
            usuario=self.user,
            modalidade="corrida",
            inicio_em=timezone.now(),
            duracao_seg=1800, # 30 min
            calorias=300
        )
        MetricasCorrida.objects.create(
            sessao=sessao1,
            distancia_km=5.0,
            ritmo_medio_seg_km=360,
            fc_media=150
        )

        SessaoAtividade.objects.create(
            usuario=self.user,
            modalidade="musculacao",
            inicio_em=timezone.now(),
            duracao_seg=3600, # 60 min
            calorias=400
        )

        response = self.client.get(self.url_dashboard)
        data = response.data

        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
        self.assertEqual(data['total_sessoes'], 2)

        self.assertEqual(data['duracao_total_segundos'], 5400)
        
        self.assertEqual(data['calorias_totais'], 700)

        self.assertEqual(data['por_modalidade']['corrida']['sessoes'], 1)
        self.assertEqual(data['por_modalidade']['corrida']['distancia_total_km'], 5.0)

    def test_dashboard_nao_mistura_usuarios(self):
        
        outro_usuario = Usuario.objects.create(
            nome='Intruso', 
            email='intruso@teste.com', 
            hash_senha='123'
        )
        
        SessaoAtividade.objects.create(
            usuario=outro_usuario,
            modalidade="corrida",
            inicio_em=timezone.now(),
            duracao_seg=1000,
            calorias=1000
        )

        response = self.client.get(self.url_dashboard)

        self.assertEqual(response.data['total_sessoes'], 0)
        self.assertEqual(response.data['calorias_totais'], 0)                      

class SerieMusculacaoTests(APITestCase):
    
    def setUp(self):
        self.user = Usuario.objects.create(nome='Bodybuilder', email='gym@teste.com', hash_senha='123')
        self.client.force_authenticate(user=self.user)
        
        self.exercicio = Exercicio.objects.create(nome="Supino Reto")
        self.sessao = SessaoAtividade.objects.create(
            usuario=self.user, 
            modalidade="musculacao", 
            inicio_em=timezone.now()
        )
        self.url_series = reverse('series-musculacao-list')

    def test_criar_serie_com_sucesso(self):
        payload = {
            "sessao": self.sessao.id,
            "exercicio": self.exercicio.id,
            "repeticoes": 10,
            "carga_kg": 20.5
        }
        
        response = self.client.post(self.url_series, payload)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SerieMusculacao.objects.count(), 1)

    def test_impedir_serie_em_sessao_alheia(self):
        outro = Usuario.objects.create(nome='Outro', email='outro@t.com', hash_senha='123')
        sessao_do_outro = SessaoAtividade.objects.create(
            usuario=outro, 
            modalidade="musculacao", 
            inicio_em=timezone.now()
        )
        
        payload = {
            "sessao": sessao_do_outro.id,
            "exercicio": self.exercicio.id,
            "repeticoes": 10,
            "carga_kg": 10
        }
        
        response = self.client.post(self.url_series, payload)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)