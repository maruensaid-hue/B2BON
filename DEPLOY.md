# Deploy em produção — B2B ON (Onda G)

Guia passo a passo para colocar a plataforma no ar usando só serviços
com camada gratuita real: **Neon** (Postgres), **Neo4j AuraDB Free**
(grafo), **Render** (backend) e **Cloudflare Pages** (frontend). Cada
passo abaixo exige uma conta pessoal sua nesses serviços — não é algo
que possa ser automatizado por aqui.

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

## 5. Frontend — Cloudflare Pages

1. Em https://pages.cloudflare.com, conecte o mesmo repositório GitHub.
2. Configuração do build:
   - Diretório raiz: `frontend`
   - Comando de build: `npm run build`
   - Diretório de saída: `dist`
3. Variável de ambiente do projeto: `VITE_API_BASE_URL` = URL pública
   do serviço no Render + `/api/v1` (ex.:
   `https://b2bon-api.onrender.com/api/v1`).
4. Deploy. O arquivo `frontend/public/_redirects` já está no repo —
   garante que rotas como `/crm` funcionem ao recarregar a página.

## 6. Fechar o CORS

Volte ao Render, atualize `CORS_ORIGINS` para incluir a URL real do
Cloudflare Pages (ex.: `["https://b2bon.pages.dev"]`, ou o domínio
próprio se configurar um) e faça redeploy do serviço.

## Verificação final

Acesse a URL do Cloudflare Pages, faça login com o admin criado no
passo 4, confirme que Dashboard/CRM/Prospecção/MAP/Rede Social/Admin
carregam dados reais do Neon+AuraDB em produção.
