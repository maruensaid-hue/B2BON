# Ambiente de teste (staging) — separado de produção

Guia pra ter dois ambientes rodando ao mesmo tempo: **produção**
(`master`, o que seus clientes usam hoje, ninguém deve tocar) e
**staging** (branch `staging`, onde a gente constrói/testa o que vier
do master prompt e qualquer coisa nova, sem risco pro que já está no
ar). Segue o mesmo espírito do `DEPLOY.md` — cada passo de infra é
algo que só você consegue fazer nos painéis (Render/Neon/Cloudflare/
GitHub), eu não tenho acesso a nenhum deles.

## Por que esse desenho é seguro (mesmo usando dados reais)

Você decidiu usar um **branch do Neon com os dados reais** dos seus
clientes no staging (mais realista pra testar) — isso é uma escolha
válida, mas exige alguns cuidados deliberados pra um ambiente "de
teste" não conseguir, por acidente, mandar mensagem de verdade pra um
cliente de verdade:

1. **Chave de criptografia diferente** (`CONFIGURACAO_WHATSAPP_
   ENCRYPTION_KEY`) — as credenciais de WhatsApp/SMTP de cada tenant
   ficam criptografadas no banco. Se o staging usar uma chave
   *diferente* da produção, essas credenciais copiadas junto com o
   branch do banco **não conseguem ser decifradas** no staging — o
   sistema já trata isso com segurança (mostra "credencial pode estar
   corrompida", pede pra reconfigurar, sem travar nada — mesmo
   comportamento já usado quando uma chave é rotacionada de verdade).
   Isso é a rede de segurança principal: mesmo copiando o banco de
   produção inteiro, nenhuma credencial real de canal continua
   funcionando no staging sem alguém digitar ela de novo lá.
2. **Sem `SENDGRID_API_KEY`/`SMTP_HOST` global no staging** — sem isso
   configurado, o sistema já cai automaticamente num modo "desativado
   e honesto" (não manda nada, avisa claramente que não está
   configurado) em vez de fingir sucesso. Isso cobre o e-mail
   compartilhado da plataforma.
3. **Sem disparo automático (cron) no staging** — o agendador que
   dispara cadência/campanha/e-mail de verdade continua sendo só o
   GitHub Actions que já existe, apontado só pra produção. Staging não
   ganha um cron automático por padrão — você só roda uma ação
   manualmente quando estiver testando algo específico.
4. **Mesmo cuidado de acesso que produção** — como o banco carrega
   dados reais de clientes, trate a URL/credenciais do staging com o
   mesmo cuidado (não compartilhe a URL publicamente, não deixe sem
   senha).

## Passo 1 — Git (já feito)

Branch `staging` criada a partir do `master` atual, sem nenhuma
diferença de código por enquanto. Todo trabalho novo (master prompt,
IA, etc.) vai acontecer nela — `master`/produção só recebe algo depois
que você aprovar explicitamente um merge, do mesmo jeito que já
aprovamos cada commit/push nesta sessão.

## Passo 2 — Banco de dados (Neon)

1. Entre no seu projeto Neon (o mesmo de produção).
2. Vá em **Branches** → **Create branch**.
3. Nomeie como `staging`, origem = o branch de produção (`main`/
   `production`, o que você já usa hoje). O Neon cria uma cópia
   instantânea (copy-on-write) — não duplica o espaço em disco de
   verdade até algo mudar.
4. Copie a **connection string** desse branch novo (é diferente da de
   produção, mesmo formato `postgresql://...?sslmode=require`).

## Passo 3 — Backend (Render)

**Não use "Blueprint"/`render.yaml`** pra isso — esse arquivo já
gerencia o serviço de produção (`b2bon-api`), e eu não quero arriscar
o Render tentar "reconciliar" os dois serviços num só blueprint. Crie
um serviço novo, manual:

1. Render → **New** → **Web Service** (não Blueprint).
2. Conecte o mesmo repositório do GitHub.
3. **Branch**: `staging` (esse é o ponto que garante que esse serviço
   nunca roda código de produção nem vice-versa).
4. Nome: `b2bon-api-staging` (ou o que preferir — só não repita o nome
   do serviço de produção).
5. Runtime: Docker, mesmo `Dockerfile` do repositório (igual produção).
6. Plano: free está OK pra teste.
7. Variáveis de ambiente — **copie os nomes do `render.yaml`, mas com
   valores próprios**:
   - `DATABASE_URL`: a connection string do branch `staging` do Neon
     (Passo 2), **não** a de produção.
   - `JWT_SECRET_KEY` e `SECRET_KEY`: gere valores novos e diferentes
     dos de produção (`python -c "import secrets; print(secrets.token_urlsafe(48))"`
     duas vezes) — assim um token/link gerado num ambiente nunca é
     válido no outro.
   - `CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY`: gere um valor novo
     (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
     — **de propósito diferente** do de produção (é a rede de
     segurança do item 1 acima).
   - `ANTHROPIC_API_KEY`: pode reaproveitar a mesma chave de produção
     (mesmo provedor, mesmo billing) — só fique atento que uso no
     staging conta pro mesmo limite/custo da conta.
   - `CRON_SECRET`: gere um valor novo, diferente do de produção — e
     **não** adicione a URL deste serviço em
     `.github/workflows/cron-envios.yml` (isso continua apontando só
     pra produção; ver item 3 da seção acima).
   - `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD`: pode deixar **vazio**
     por enquanto — o sistema já trata Neo4j fora do ar sem quebrar
     nada (é literalmente o mesmo comportamento de quando o Aura Free
     de produção pausou por inatividade). Se algum dia o trabalho do
     Business Graph precisar de um Neo4j de teste de verdade, criamos
     uma instância AuraDB Free separada nessa hora.
   - `GOOGLE_OAUTH_CLIENT_ID`: pode deixar vazio (login Google fica
     desabilitado no staging, sem problema).
   - `CORS_ORIGINS`: a URL do frontend de staging (Passo 4) —
     `["https://b2bon-staging.<seu-worker>.workers.dev"]`.
   - **Não copie `SENDGRID_API_KEY`** — deixe essa variável de fora
     completamente (item 2 da seção de segurança acima).
8. Deploy. Confirme que o healthcheck (`/health`) fica verde.

## Passo 4 — Frontend (Cloudflare Workers)

O fluxo unificado atual do Cloudflare ("Create an app" → Workers) tem
alguns detalhes que não são óbvios — confirmados na prática ao montar
o `b2bon-staging` real:

1. Cloudflare → **Workers & Pages** → **Create** → conecte o mesmo
   repositório do GitHub.
2. Nome do projeto: `b2bon-staging` (evite reusar o nome do de
   produção, que é `b2bon`).
3. **Caminho/Diretório raiz**: `frontend` — **não** deixe `/` (raiz do
   repositório). O `package.json` e o `wrangler.toml` do frontend
   vivem em `frontend/`, não na raiz; com `/` o `npm run build` falha
   por não achar `package.json`.
4. Build command / Deploy command: `npm run build` / `npx wrangler
   deploy` (o wizard já sugere esses valores certos, só confirme).
5. Variável de build (**não** "Runtime variables" — o painel separa
   os dois; a de build fica em **Configurações → Build → Variáveis e
   segredos**): `VITE_API_BASE_URL` = a URL do backend de staging
   (Passo 3) + `/api/v1` (ex.:
   `https://b2bon-api-staging.onrender.com/api/v1`) — **isso é
   gravado no bundle na hora do build**, então precisa estar certo
   antes de deployar, não é algo pra trocar depois em runtime.
6. **Ramificação de produção**: o seletor de branch da tela de
   criação nem sempre "pega" — depois de criar o projeto, confirme em
   **Configurações → Build → Controle da ramificação → Ramificação de
   produção** que está `staging`, não `master` (o padrão do GitHub).
   Se builds antigos aparecerem marcados `master` no histórico de
   implantações, é sinal de que esse campo ainda não tinha sido
   corrigido quando eles rodaram.
7. Ignore o aviso amarelo sobre permissões do token de API
   relacionadas a `email_routing` — é sobre um recurso do Cloudflare
   sem relação com hospedar o Worker, não bloqueia o deploy.
8. **Pra disparar um novo build depois de mudar algo em
   Configurações** (ex.: corrigir a branch): o botão "Nova
   implantação" no topo da página abre um uploader de arquivo
   estático manual (fluxo errado pra esse projeto, que é conectado ao
   Git). O jeito certo é dar um push de verdade na branch `staging`
   (mesmo um commit vazio, `git commit --allow-empty`) — isso dispara
   o webhook do Cloudflare e builda a partir do Git de novo, já com a
   branch/configuração corrigida.
9. Depois do primeiro deploy, o Cloudflare pode sugerir automaticamente
   um PR pra atualizar `frontend/wrangler.toml` (`name =
   'b2bon-staging'`) — é só informativo, pra manter o arquivo
   consistente com o nome do projeto; não bloqueia nada, pode revisar
   com calma depois.

## Passo 5 (opcional, só se/quando precisar) — Cron automático no staging

Por padrão, staging **não** dispara nada sozinho — só quando você
chamar manualmente um endpoint (Postman, `curl`, ou uma tela que a
gente construir). Se um dia for genuinely necessário testar o
comportamento agendado, a forma segura é um workflow **novo e
separado** (não adicionar jobs ao `cron-envios.yml` existente),
disparado só por `workflow_dispatch` manual — nunca num `schedule`
automático, justamente pra nunca correr o risco de mandar mensagem de
verdade pra um cliente de verdade sem alguém decidir isso na hora.

## Promovendo staging → produção

Quando algo testado no staging estiver pronto pra virar produção de
verdade: PR ou merge de `staging` → `master` (eu sempre aviso e peço
"posso subir?" antes, do mesmo jeito que já faço pra cada commit nesta
sessão — merge pra `master` não é diferente disso, só que a origem é
uma branch em vez de mudanças locais). O deploy em si continua
automático como já é hoje (push em `master` → Render/Cloudflare de
produção atualizam sozinhos).

## Resumo do que fica igual e do que fica diferente

| | Produção | Staging |
|---|---|---|
| Branch | `master` | `staging` |
| Banco | Neon (branch de produção) | Neon (branch `staging`, cópia) |
| Backend | `b2bon-api` (Render) | `b2bon-api-staging` (Render) — `https://b2bon-api-staging.onrender.com` |
| Frontend | Worker de produção | `b2bon-staging` (Worker) — `https://b2bon-staging.maruen-said.workers.dev` |
| Credenciais de canal (WhatsApp/e-mail por tenant) | funcionam | copiadas mas **ilegíveis** (chave de criptografia diferente) |
| E-mail/WhatsApp compartilhado da plataforma | configurado | **desativado** (sem `SENDGRID_API_KEY`) |
| Cron automático | sim (GitHub Actions existente) | **não**, por padrão |
| Deploy | automático em push no `master` | automático em push no `staging` |

**Status (2026-09-17): ambiente staging totalmente operacional** —
backend, banco e frontend no ar, CORS liberado, login testado e
funcionando de ponta a ponta.
