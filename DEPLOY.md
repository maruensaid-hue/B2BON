# Deploy em produção — B2B ON (Onda G)

Guia passo a passo para colocar a plataforma no ar usando só serviços
com camada gratuita real: **Neon** (Postgres), **Neo4j AuraDB Free**
(grafo), **Render** (backend) e **Cloudflare Workers** (frontend
estático — a Cloudflare descontinuou o "Pages" como produto separado
em 2026, unificando tudo em "Workers"). Cada passo abaixo exige uma
conta pessoal sua nesses serviços — não é algo que possa ser
automatizado por aqui.

Já foi feito uma vez com sucesso: backend em
`https://b2bon-api.onrender.com`, frontend em
`https://b2bon.maruen-said.workers.dev`. Este guia documenta o caminho
real percorrido (inclui os desvios da versão original do plano).

## 1. Banco de dados — Neon

1. Crie uma conta em https://neon.tech (sem cartão).
2. Crie um projeto novo (ex.: `b2bon`), banco `predator`.
3. Copie a **connection string** — já vem com `?sslmode=require` no
   final. Guarde para o passo 3.

## 2. Grafo — Neo4j AuraDB Free

1. Crie uma conta em https://neo4j.com/cloud/aura-free/.
2. Crie uma instância **AuraDB Free**. Anote usuário, senha e a URI
   (formato `neo4j+s://xxxxxxxx.databases.neo4j.io`).

## 3. Backend — Render

1. Suba este repositório no GitHub, se ainda não estiver.
2. Em https://render.com, "New" → "Blueprint" → aponte para o repo.
   O Render lê o `render.yaml` da raiz e propõe o serviço
   `b2bon-api` automaticamente.
3. Preencha as variáveis marcadas como secretas no painel:
   - `DATABASE_URL`: a connection string do Neon (passo 1.3).
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: do passo 2.
   - `ANTHROPIC_API_KEY`: sua chave da Anthropic (necessária para os
     recursos de IA — enriquecimento por site, qualificação, script de
     resgate do MAP).
   - `JWT_SECRET_KEY` e `SECRET_KEY`: gere dois valores aleatórios
     longos (ex.: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
     duas vezes, um para cada).
   - `GOOGLE_OAUTH_CLIENT_ID`: se for usar login com Google agora;
     pode deixar vazio por enquanto (o botão já avisa que precisa
     dessa configuração).
   - `CORS_ORIGINS`: por ora, `["http://localhost:5173"]` — você
     atualiza no passo 5 com a URL real do frontend.
4. Deploy. O `CMD` do Docker roda `alembic upgrade head` sozinho antes
   de subir o Uvicorn — o schema completo é criado no Neon nesse
   primeiro deploy.
5. **Limitação conhecida do plano free do Render**: sem disco
   persistente — arquivos enviados em `/materiais` (upload de ofertas)
   não sobrevivem a um redeploy. Aceitável para o estágio de cliente
   zero; reavaliar se isso virar um uso real.

## 4. Primeiro tenant real (CyberFort)

Mais simples rodar **do seu computador**, apontando para o Neon direto,
em vez de depender do shell do Render:

```bash
DATABASE_URL="<connection string do Neon>" python scripts/bootstrap_tenant.py
```

Mesmo script já usado localmente (Onda A) — pede tenant, plano,
admin e senha interativamente.

## 5. Frontend — Cloudflare Workers (site estático)

A Cloudflare não oferece mais "Pages" como fluxo separado — o caminho
real, hoje, é criar um **Worker** a partir de um repositório Git,
configurado como ativos estáticos puros (sem código de servidor):

1. Em https://dash.cloudflare.com, vá em **Computação → Workers e
   Pages** (pode estar direto na barra lateral) → **"Criar
   aplicativo"** → **"Continue with GitHub"** → selecione o repo
   `B2BON`.
2. Na tela "Configure seu aplicativo":
   - **Comando da build**: `cd frontend && npm install && npm run build`
   - **Comando de implantação**: `cd frontend && npx wrangler deploy`
     (o campo já vem preenchido com `npx wrangler deploy` sozinho —
     é preciso adicionar o `cd frontend &&` na frente).
3. O arquivo `frontend/wrangler.toml` já está no repo, configurando o
   Worker como ativos estáticos puros (`[assets] directory = "./dist"`,
   `not_found_handling = "single-page-application"` — cobre o mesmo
   papel que o antigo `_redirects` do Pages clássico cobria; **não**
   recriar um `_redirects`, os dois mecanismos juntos causam um loop
   infinito de redirecionamento e o deploy falha).
4. Depois do primeiro deploy, vá em **Configurações → Build** (não em
   "Variáveis e segredos" da aba principal — aquela seção é só para
   variáveis de **tempo de execução**, bloqueada para Workers só de
   ativos estáticos) e adicione, na seção "Variáveis e segredos" **de
   dentro de Build**:
   - **Nome**: `VITE_API_BASE_URL`
   - **Valor**: URL pública do serviço no Render + `/api/v1` (ex.:
     `https://b2bon-api.onrender.com/api/v1`)

   O Vite grava esse valor dentro do JavaScript já no momento do
   `npm run build` (não é lido em tempo de execução) — se essa
   variável for adicionada **depois** do primeiro deploy, é preciso
   disparar um novo deploy (um novo commit/push é o jeito mais
   confiável; o botão "Nova implantação" do painel abre um upload
   manual de arquivos, não um rebuild a partir do Git).
5. A URL final fica em `https://<nome-do-worker>.<sua-conta>.workers.dev`.

## 6. Fechar o CORS

Volte ao Render, no serviço `b2bon-api`, aba **Environment**, atualize
`CORS_ORIGINS` para a URL real do Worker (ex.:
`https://b2bon.maruen-said.workers.dev` — texto simples, sem colchetes
nem aspas; o campo aceita os dois formatos) e salve — o Render redeploya
sozinho.

## Verificação final

Acesse a URL do Worker, faça login com o admin criado no passo 4,
confirme que Dashboard/CRM/Prospecção/MAP/Rede Social/Admin carregam
dados reais do Neon+AuraDB em produção.
