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
   - `WHATSAPP_WEBHOOK_VERIFY_TOKEN`: gere com
     `python -c "import secrets; print(secrets.token_urlsafe(32))"` — é o
     valor colado em Meta for Developers > WhatsApp > Step 2 (Production
     setup) > Configure Webhooks > **Verify token** (precisa ser
     idêntico dos dois lados). A **Callback URL** correspondente é
     `https://<seu-backend>/api/v1/webhooks/whatsapp/meta`.
4. Deploy. O `CMD` do Docker roda `alembic upgrade head` sozinho antes
   de subir o Uvicorn — o schema completo é criado no Neon nesse
   primeiro deploy.
5. Materiais de oferta (`/materiais`) são salvos como blob direto no
   Postgres — não dependem mais de disco persistente, sobrevivem a
   qualquer redeploy mesmo no plano free do Render.

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

## 7. Disparo agendado de envio, lembretes e NPS (Onda I / Onda J)

O Render free não tem worker/cron nativo — sem esse passo, mensagens
aprovadas ficam pra sempre "agendadas" e nunca saem, lembretes de
reunião (D-1/H-2) nunca disparam e pesquisas de NPS nunca são
disparadas, porque nada chama esses dispatchers sozinho. Quem chama é
um **GitHub Actions agendado** (`.github/workflows/cron-envios.yml`, já
no repo, roda a cada 15 minutos de graça, chamando os dois endpoints
abaixo em sequência):

1. Gere o segredo: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Cole o mesmo valor em dois lugares:
   - Render → `b2bon-api` → **Environment** → `CRON_SECRET`.
   - GitHub → repositório → **Settings → Secrets and variables →
     Actions → New repository secret** → nome `CRON_SECRET`.
3. Se a URL do backend não for `https://b2bon-api.onrender.com/api/v1`,
   defina também uma **Actions variable** (não secret) chamada
   `API_BASE_URL` com a URL certa — o workflow já tem esse valor como
   padrão.
4. Confirme em **Actions** (aba do GitHub) que o workflow "Disparar
   envios pendentes" aparece e roda sem erro (pode disparar manual pelo
   botão "Run workflow" pra testar sem esperar os 15 minutos).

Efeito colateral útil: como o Render free "dorme" sem tráfego, esse
ping a cada 15 minutos também mantém o serviço acordado.

## Verificação final

Acesse a URL do Worker, faça login com o admin criado no passo 4,
confirme que Dashboard/CRM/Prospecção/MAP/Rede Social/Admin carregam
dados reais do Neon+AuraDB em produção.
