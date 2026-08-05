# B2B ON

Plataforma SaaS multi-tenant da CyberFort com quatro módulos:

- **CRM** — funil de negócios (estágios, atividades, custo de aquisição).
- **Rede Social** — rede B2B entre empresas do ecossistema B2B ON (perfil,
  diretório, conexões, mensagens, indicações). É o único módulo acessível
  por um tenant sem licença ativa (entrada via convite-vitrine).
- **MAP** — motor de risco de churn dos próprios tenants clientes
  (score de risco, alertas, script de resgate assistido por IA).
- **PREDATOR** — motor de prospecção assistida por IA: ICP, geração de
  listas a partir da Receita Federal, enriquecimento, cadências
  multicanal (e-mail/WhatsApp/LinkedIn) com fila de aprovação humana,
  disparo agendado, rastreio de abertura de e-mail, qualificação de
  reuniões e dossiê automático.

Para o funcionamento de cada módulo do ponto de vista do usuário final,
incluindo a diferença entre os planos de licença (franquia, limite de
usuários, tier vitrine), veja o [Manual do Usuário](MANUAL_DO_USUARIO.md).

Para colocar em produção (Render + Neon + Neo4j AuraDB + Cloudflare
Workers), veja o [DEPLOY.md](DEPLOY.md).

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 + Pydantic v2, Alembic para
  migrações, Postgres em produção (Neon) / SQLite em desenvolvimento,
  Neo4j (grafo de relacionamento entre tenants), Anthropic (recursos
  de IA — enriquecimento, qualificação, script de resgate).
- **Frontend**: React + TypeScript + Vite, Tailwind v4 (tema
  configurado em `frontend/src/index.css`), PWA instalável.
- **Autenticação**: JWT (`tenant_id`/`papel` no claim), multi-tenant
  por linha (toda tabela de negócio carrega `tenant_id`).

## Estrutura do repositório

```
app/
  api/v1/        rotas por módulo (crm, rede_social, motor, icp,
                  cadencias, aprovacoes, envios, reunioes, ...)
  core/          settings (variáveis de ambiente)
  db/            engine/sessão SQLAlchemy
  models/        modelos ORM
  schemas/       schemas Pydantic (request/response)
  services/      regra de negócio
  providers/     integrações externas (Receita Federal, BrasilAPI,
                  WhatsApp, e-mail/SMTP, calendário, IA)
alembic/         migrações do schema
frontend/        SPA React (uma pasta em src/pages por módulo/tela)
scripts/         scripts operacionais (bootstrap de tenant, carga de
                  recorte da Receita Federal)
tests/           unit/ e integration/, pytest
```

## Rodando localmente

Backend (SQLite local, sem dependências externas):

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
cp .env.example .env
python -m uvicorn app.main:app --reload
```

O primeiro tenant é criado com `python scripts/bootstrap_tenant.py`
(interativo — pede nome do tenant, plano, e-mail e senha do admin).

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Copie `frontend/.env.example` para `frontend/.env` — o padrão já é
`VITE_API_BASE_URL=http://localhost:8000/api/v1`, certo para dev local.

## Testes

```bash
python -m pytest -q
```

`tests/unit/` cobre regra de negócio isolada; `tests/integration/`
sobe a aplicação inteira via `TestClient` contra um SQLite temporário
por teste (`tests/conftest.py`).

## Variáveis de ambiente

Veja `.env.example` para a lista completa comentada. As mais
relevantes para rodar em produção (não têm default seguro):
`DATABASE_URL`, `JWT_SECRET_KEY`, `SECRET_KEY`, `CORS_ORIGINS`,
`CRON_SECRET`, `ANTHROPIC_API_KEY`.
