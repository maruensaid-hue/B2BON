# Produção com o papel restrito (RLS) — passo a passo

Objetivo: fazer a API de **produção** conectar com o papel `b2bon_app` (sem superusuário e sem `BYPASSRLS`). Só depois disso o RLS passa a proteger de verdade em produção; hoje ele está criado nas
179 tabelas, mas a API conecta como `neondb_owner`, que o ignora. É o último passo para fechar o achado A01.

> **Status (2026-10-29):** executado. O papel `b2bon_app` foi criado no branch `production`, `MIGRATION_DATABASE_URL` aponta para o dono e `DATABASE_URL` para `b2bon_app`; o deploy ficou Live às 19:55 e a produção aparece conectada como `b2bon_app`. O A01 foi encerrado no mesmo dia por decisão do PO, sem a observação de 24 a 48 horas (D-112). Este documento fica como referência e como roteiro de reversão. Na execução real as senhas do `b2bon_app` e do `neondb_owner` passaram pela conversa; o PO informou que já foram trocadas.

Estado de partida (confirmado em 2026-10-29): as duas migrações (`e7a9c1d3f5b8` e `a3c5e7b9d1f2`) já rodaram em produção; o branch `production` do Neon tem só o papel `neondb_owner`; o staging já roda assim
desde o mesmo dia. Nada aqui altera dado nem esquema.

**Regras:** nunca cole senha ou URL de conexão no chat; ao pedir ajuda, mande só o final do log e o texto do erro.

---

## Passo 0 — Antes de começar (não pule)

1. **Roteiro no staging com a etapa 2.** No staging (que já roda com `b2bon_app`), abra e use: Aprovações, Campanhas, Cadências, Configuração, Admin, Shoal (feed, comentar, curtir, mensagem, sala) e Registro de Oportunidade,
   e crie um negócio. Avise "terminei" e peça a leitura dos logs. **Só siga se não houver erro de RLS, de permissão nem 500** (o 500 de WhatsApp do staging é pendência conhecida e não conta).
2. **Janela de baixo uso**, com Neon e Render abertos e uns 30 minutos livres.
3. Tenha em mãos o valor atual do `DATABASE_URL` de produção (Render → serviço `b2bon-api` → Environment). Ele é a URL do dono e será a sua reversão.

## Passo 1 — Criar o papel no Neon (branch de PRODUÇÃO)

1. Neon → projeto `b2bon` → no seletor de branch escolha **`production`** (não `b2bon-staging`) → **SQL Editor**.
2. Invente uma senha **nova e diferente da do staging**: só letras e números, 24 caracteres ou mais (evita problema dentro da URL). Guarde no gerenciador de senhas.
3. Cole o SQL abaixo, troque as duas ocorrências de `SUA_SENHA_AQUI` e clique em **Run**:

```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'b2bon_app') THEN
    CREATE ROLE b2bon_app LOGIN PASSWORD 'SUA_SENHA_AQUI' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  ELSE
    ALTER ROLE b2bon_app LOGIN PASSWORD 'SUA_SENHA_AQUI' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO b2bon_app', current_database()); END $$;
GRANT USAGE ON SCHEMA public TO b2bon_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO b2bon_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO b2bon_app;
REVOKE ALL ON alembic_version FROM b2bon_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO b2bon_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO b2bon_app;
```

4. Confira (mesmo SQL Editor, ainda no branch `production`):

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'b2bon_app';
```

   Precisa voltar `b2bon_app | f | f`. Se `rolbypassrls` vier `t`, **pare** e não troque o `DATABASE_URL`.

## Passo 2 — Trocar as variáveis no Render (serviço `b2bon-api`, produção)

Faça as duas mudanças e só então clique em **Save** (gera um deploy só).

1. **`MIGRATION_DATABASE_URL`** (criar): cole o valor atual do `DATABASE_URL` (a URL do dono, usuário `neondb_owner`). É a que o Alembic usa na subida do serviço.
2. **`DATABASE_URL`** (editar): mesma URL de hoje, trocando só o usuário e a senha:

```
postgresql://b2bon_app:SUA_SENHA_AQUI@<mesmo host da URL atual>/neondb?sslmode=require
```

   Use o **mesmo host** da URL atual (o do pooler) e não acrescente `channel_binding` (no staging, essa opção duplicada derrubou o deploy).
3. **Save** e acompanhe o deploy até **Live**.
   - Se o deploy **falhar**, a versão anterior continua no ar (nada para correr). Quase sempre é senha errada em `MIGRATION_DATABASE_URL` ou espaço/quebra de linha colado junto. Mande só o final do log.

## Passo 3 — Conferir (avise "Live" e eu verifico)

Eu confiro: (a) no Neon, que a produção aparece conectada como `b2bon_app`; (b) nos logs, que não há 500, erro de RLS nem de permissão; (c) a latência das rotas principais.

Você confere na tela, com um usuário comum e um administrador: login, CRM (abrir e editar um negócio), Prospecção, Relatório de Entrega, Aprovações e o Shoal.

Depois, rode os agendamentos uma vez à mão: GitHub → Actions → o workflow de cron (`cron-envios.yml`) → **Run workflow**. Os passos precisam terminar verdes. Os cron rodam em contexto de sistema (acesso total), então o risco é baixo, mas é a única forma de ver todos funcionando agora em vez de esperar o horário.

## Passo 4 — Observação por 24 a 48 horas

- Peça a leitura dos logs no fim do primeiro dia e do segundo. Procuro: `status=500`, `InsufficientPrivilege`, `row-level security`, `permission denied`, falha de cron.
- **Sinal que NÃO gera erro:** tela ou relatório vindo vazio ou com zeros onde antes havia dado (o RLS devolve zero linhas, não exceção). Se alguém reportar algo "sumido", é este caso: avise na hora e faça a reversão abaixo.
- Mudança visível esperada: quem não é parte de uma sala corporativa recebe "não encontrado" (404) em vez de "sem permissão" (403). Não há acesso em nenhum dos dois casos.

## Reversão (segundos, sem migração, sem perda de dado)

Render → `b2bon-api` → Environment → `DATABASE_URL` = a URL antiga do dono (a que você guardou no Passo 0) → Save → esperar **Live**. O RLS deixa de valer e tudo volta ao que era. `MIGRATION_DATABASE_URL` e o papel `b2bon_app` podem ficar.

## Depois que estiver estável

1. Apague o arquivo `papel.sql` da raiz do repositório (está vazio e não vai para o Git, mas não precisa existir).
2. **Não mexa** nos secrets do GitHub Actions que carregam o recorte de CNPJ: eles usam a URL do dono e só tocam tabelas globais (sem dado de empresa); continuam como estão.
3. Opcional: trocar a senha do `neondb_owner` e atualizar `MIGRATION_DATABASE_URL` (Render) e os secrets do GitHub que a usam.
4. Avise "estável" que eu atualizo o D-111 e o `RLS.md` para "ligado em produção". **A01 só passa a "resolvido" nesse momento.**

## Limites que continuam valendo

Rotas só de `super_admin`, cron e webhooks têm acesso total no banco por desenho (descrito em `RLS.md`, seção 7). O RLS não protege contra SQL arbitrário executado pela própria aplicação.
