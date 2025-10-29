CREATE TABLE usuarios (
  id BIGSERIAL PRIMARY KEY,
  nome VARCHAR(120) NOT NULL,
  email VARCHAR(254) UNIQUE NOT NULL,
  hash_senha TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE exercicios (
  id BIGSERIAL PRIMARY KEY,
  nome VARCHAR(120) NOT NULL,
  grupo_muscular VARCHAR(60),
  equipamento VARCHAR(60)
);

CREATE TABLE sessoes_atividade (
  id BIGSERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  modalidade VARCHAR(20) NOT NULL,
  inicio_em TIMESTAMPTZ NOT NULL,
  duracao_seg INTEGER CHECK (duracao_seg >= 0),
  calorias INTEGER CHECK (calorias >= 0),
  observacoes TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_sessoes_modalidade CHECK (modalidade IN ('corrida','ciclismo','musculacao'))
);

CREATE INDEX idx_sessoes_usuario_tempo ON sessoes_atividade(usuario_id, inicio_em DESC);
CREATE INDEX idx_sessoes_modalidade ON sessoes_atividade(modalidade);

CREATE TABLE metricas_corrida (
  sessao_id BIGINT PRIMARY KEY REFERENCES sessoes_atividade(id) ON DELETE CASCADE,
  distancia_km NUMERIC(7,2) CHECK (distancia_km >= 0),
  ritmo_medio_seg_km INTEGER CHECK (ritmo_medio_seg_km >= 0),
  fc_media SMALLINT
);

CREATE TABLE metricas_ciclismo (
  sessao_id BIGINT PRIMARY KEY REFERENCES sessoes_atividade(id) ON DELETE CASCADE,
  distancia_km NUMERIC(7,2) CHECK (distancia_km >= 0),
  velocidade_media_kmh NUMERIC(5,2) CHECK (velocidade_media_kmh >= 0),
  fc_media SMALLINT
);

CREATE TABLE series_musculacao (
  id BIGSERIAL PRIMARY KEY,
  sessao_id BIGINT NOT NULL REFERENCES sessoes_atividade(id) ON DELETE CASCADE,
  exercicio_id BIGINT NOT NULL REFERENCES exercicios(id),
  ordem_serie INTEGER NOT NULL CHECK (ordem_serie >= 1),
  repeticoes INTEGER CHECK (repeticoes >= 0),
  carga_kg NUMERIC(6,2) CHECK (carga_kg >= 0)
);

CREATE INDEX idx_series_sessao ON series_musculacao(sessao_id);
CREATE INDEX idx_series_exercicio ON series_musculacao(exercicio_id);

CREATE TABLE metas_habito (
  id BIGSERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  titulo VARCHAR(120) NOT NULL,
  modalidade VARCHAR(20) NOT NULL,
  data_inicio DATE NOT NULL,
  data_fim DATE,
  frequencia_semana SMALLINT,
  distancia_meta_km NUMERIC(7,2),
  duracao_meta_min INTEGER,
  sessoes_meta INTEGER,
  ativo BOOLEAN NOT NULL DEFAULT true,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_metas_modalidade CHECK (modalidade IN ('corrida','ciclismo','musculacao')),
  CONSTRAINT ck_metas_alvo CHECK (
    frequencia_semana IS NOT NULL
    OR distancia_meta_km IS NOT NULL
    OR duracao_meta_min IS NOT NULL
    OR sessoes_meta IS NOT NULL
  )
);

CREATE TABLE marcacoes_habito (
  id BIGSERIAL PRIMARY KEY,
  meta_id BIGINT NOT NULL REFERENCES metas_habito(id) ON DELETE CASCADE,
  usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  data DATE NOT NULL,
  sessao_id BIGINT REFERENCES sessoes_atividade(id) ON DELETE SET NULL,
  concluido BOOLEAN NOT NULL DEFAULT true,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (meta_id, data)
);
