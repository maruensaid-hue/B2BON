# 08 — Segurança alvo (§60–62, §79–80)

> Consolidação da Fase 17 ao final deste documento. Estado e riscos
> anteriores: `SECURITY_BOUNDARIES.md`.

- **Fase responsável**: contínuo; consolidação na 17
- **Estado atual / ponto de partida**: Estado atual e riscos priorizados: `SECURITY_BOUNDARIES.md`.


## Fase 17 — revisão e hardening

| Área | O que foi verificado ou feito | Evidência |
|---|---|---|
| Isolamento tenant × tenant | Varredura de TODAS as rotas GET com ids existentes: nenhum dado privado de outro tenant; controle positivo prova que os ids chegam aos dados; nenhuma resposta 5xx | `test_varredura_isolamento.py` |
| Barreira Buy × Sell | Mesma varredura: dado do comprador nunca aparece fora de `/procurement` | idem, + fitness da Fase 10 |
| Prompt injection | **Achado corrigido**: prompts antigos usavam a tag `CONTEUDO_EXTERNO_NAO_CONFIAVEL` sem neutralizar (site, pergunta de outra empresa podiam fechar o bloco); mensagem de lead ia sem delimitação. Agora neutralizadas/delimitadas; teste ponta a ponta de 5 superfícies | `prompt_seguro.py`, `test_seguranca_ia.py` |
| Isolamento do RAG | Já coberto (Brain por tenant, só itens compartilháveis para fora, procurement fora do Brain) | `test_inteligencia_brain.py`, `test_public_procurement.py` |
| Teto de uso de IA | **Achado corrigido**: 9 rotas com IA sem limite por tenant; fitness function exige limite ou gatilho automático (teto por hora do gateway) | `test_limite_ia_nas_rotas.py` |
| Segredos em log | Tokens em query string mascarados no log do httpx e no erro do sync (Fase 13) | D-043 |
| SSRF | Hosts fixos por conector, sem redirect (Fase 13) | D-042 |
| Dependências | `pip-audit`: 0 vulnerabilidades. `npm audit`: 1 alta em dependência de build (`fast-uri`, via workbox), atualizada só no lockfile → 0 | `frontend/package-lock.json` |
| Segredos padrão | A API se recusa a subir fora de SQLite com `SECRET_KEY`/`JWT_SECRET_KEY` padrão (verificado ao subir o teste de carga) | `config.validar_segredos_de_producao` |

## Ambiente de demonstração (D-082)

Rota pública sem senha (`POST /auth/demonstracao`), desligada por padrão. Cada sessão é um tenant próprio e efêmero;
o token marcado `demo` não alcança dados de outros tenants (rede de empresas, sinais entre empresas, indicações),
administração da plataforma nem ações que gerem custo, acesso ou contato externo (middleware `bloqueio_demonstracao`).
Envios do tenant de demonstração usam provedores simulados. Limites: sessões ativas, sessões por IP/hora e créditos
de IA próprios. Detalhes em `DEMONSTRACAO.md`.

D-083 (antes de ligar em produção): negação por padrão para tokens de demonstração (só as rotas das telas de produto),
todos os provedores externos simulados na requisição de demonstração (`app/services/demo/contexto.py`), tokens de
demonstração invalidados quando o recurso é desligado e limite por IP real (último X-Forwarded-For) + teto global.

## CORS: checagem prévia de rede privada (2026-10-02)

- `allow_private_network=True` no CORS: navegadores recentes pedem `Access-Control-Request-Private-Network` na
  checagem prévia; recusar quebrava o /demo no celular. Não amplia o acesso — só origens de `CORS_ORIGINS` recebem
  `Access-Control-Allow-Origin`; recusas são registradas com o motivo (logger `b2bon.cors`).
- `CORS_ORIGINS_PROPRIAS` (padrão `https://b2bon.onrender.com`): frontends da própria B2B ON publicados por este
  repositório, somados a `CORS_ORIGINS` do painel. Nunca incluir origem de terceiros aqui.

## Envio por API do cliente, avisos de entrega e lista de bloqueio (2026-10, D-106 a D-108)

- **Chaves cifradas em repouso**: `configuracao_email_api.chave_api` e `.chave_webhook` usam `TextoCriptografado` (Fernet), como as credenciais SMTP.
  A API só devolve o final da chave (`chave_mascarada`); `PUT` com chave em branco mantém a atual. Se a chave de criptografia mudar, a leitura falha de
  forma controlada (`InvalidToken`) e o aviso de eventos daquele tenant deixa de ser aceito, em vez de derrubar o processamento.
- **Aviso de eventos (`POST /webhooks/envio/eventos`, alias `/webhooks/sendgrid/eventos`) é público, mas assinado**: a assinatura (ECDSA P-256 sobre
  `timestamp + corpo`) é verificada antes de qualquer gravação. Há dois emissores legítimos: a conta da plataforma (chave global) e a conta de cada cliente
  (chave em `configuracao_email_api`). Os eventos lidos antes da verificação servem só para descobrir de quais tenants são; quando a assinatura bate com a chave de
  um tenant, **apenas os eventos desse tenant** são processados. Uma chave de cliente nunca forja entrega, bounce ou spam de outro cliente.
- **Eventos sempre dentro do tenant**: a busca da mensagem ou do destinatário de campanha usa `tenant_id` do evento e o id ecoado no envio; e-mail de sistema
  (convite, cobrança, boas-vindas) não tem esses ids e nunca alimenta a reputação do canal (incidente de 2026-10-05).
- **Pixel de abertura**: o token é HMAC (`tenant:id:assinatura`; os ids de campanha levam o prefixo `c`); token inválido não registra nada e a imagem é servida
  do mesmo jeito. A abertura é indicador aproximado, nunca base de decisão automática.
- **Lista de bloqueio** (`bloqueio_contato`): consultada no envio de toda campanha do tenant (e-mail em minúsculas; telefone pelos 10 últimos dígitos). Liberar um
  bloqueio exige `admin` ou `super_admin`; marcar "não quer receber" e ver a lista valem para qualquer usuário do tenant com acesso ao PREDATOR.
- **Reserva do disparo**: `campanha.processando_ate` impede dois processos de enviar a mesma campanha (envio imediato e agendador); a reserva vence em 10 minutos.
- **Entrada tratada como dado**: nomes, telefones e empresas colados de planilha passam por `corrigir_codificacao` (só reverte a troca de codificação
  quando o resultado é UTF-8 válido) e os marcadores `[Nome]`/`[Empresa]` são trocados por expressão regular sobre o texto, sem executar nada.
