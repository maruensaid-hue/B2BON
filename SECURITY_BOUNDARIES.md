# SECURITY_BOUNDARIES.md — B2B ON (2026-09-17)

Limites de confiança e controles de segurança que existem hoje, e os
gaps reais (não hipotéticos) encontrados na auditoria.

## 1. Isolamento entre tenants

- **Mecanismo**: coluna `tenant_id` em quase toda tabela de negócio,
  filtrada em cada query de serviço. **Não há Row-Level Security no
  banco** — o isolamento depende inteiramente de cada função de
  serviço lembrar de filtrar por `tenant_id`. Não existe teste
  automatizado genérico que garanta isso pra TODA tabela/rota (os
  testes de isolamento existentes, como o de `panel_service`
  mencionado em memória, cobrem casos específicos, não a superfície
  inteira).
- **Única exceção deliberada**: `cnpj_estabelecimento`/`cnpj_socio`
  (staging da Receita Federal) não têm `tenant_id` — são dado público
  nacional compartilhado, nunca dado autorado por um tenant. Confirmado
  lendo `app/providers/account_data/receita_federal_models.py` — sem
  isso, nenhum outro modelo do sistema deixa de ter `tenant_id`.
- **Hierarquia amplia visibilidade de forma controlada**:
  `tenant_service.tenant_ids_no_escopo` é o único caminho pelo qual um
  `admin`/`super_admin` vê dado de outro tenant — sempre a própria
  subárvore, nunca lateral/arbitrário; `NaoAutorizado` se tentar
  "zoom" num tenant fora do escopo. `user` nunca sai do próprio tenant.
- **Gap real**: isolamento é 100% disciplina de código, zero
  enforcement estrutural (RLS, schema separado, etc.). Se um novo
  endpoint esquecer de filtrar `tenant_id`, nada no banco impede o
  leak — só revisão de código.

## 2. Autenticação e autorização

- JWT HS256, mas **papel/tenant efetivos são sempre relidos do banco a
  cada request** (não do payload do token) — mudança de permissão tem
  efeito imediato, não dá pra "usar um token antigo" pra manter um
  privilégio revogado.
- Segundo mecanismo de auth, independente: chave de API de parceiro
  (SHA-256 hash, `ChaveApiParceiro`) pra API de provisionamento de
  Distribuidores — não passa pelo JWT.
- Autorização é composta de 3 eixos, sem policy engine central: papel
  (`super_admin|admin|user`), `tenant_id` (isolamento de linha) e
  hierarquia (subárvore de tenant). Mais um eixo ortogonal: licença/
  plano (`exigir_licenca_ativa`, `PlanLimitsProvider`) — bloqueia
  feature inteira independente de papel.
- **Sem ABAC/permissão por recurso individual** — não existe "usuário X
  pode editar só o negócio Y", é sempre papel + tenant + (às vezes)
  "é o vendedor responsável por esta conta" (checado ad-hoc em cada
  serviço, não uma política central).
- **Gap encontrado e corrigido (2026-09-20): escalonamento de
  privilégio via convite.** `POST /convites` (`exigir_papel("super_admin",
  "admin")`, `app/api/v1/convites.py`) autoriza QUEM CHAMA a rota, mas
  não limitava o `papel_concedido` do convite gerado — um `admin`
  comum de qualquer tenant conseguia gerar um convite com
  `papel_concedido="super_admin"` e criar (ou virar) um usuário com
  papel global de verdade, já que `super_admin` não tem escopo de
  tenant (bypassa `exigir_gestor_do_tenant`/`permitir_gestao_
  hierarquica` por completo). Corrigido em `auth_service.gerar_convite`:
  só quem já é `super_admin` pode conceder o papel `super_admin` — o
  padrão "rota autoriza quem chama, mas não valida o que ele está
  PEDINDO pro sistema fazer" é o tipo de gap que vale conferir de novo
  em qualquer rota nova que aceite um `papel`/permissão como parâmetro
  do corpo da requisição.

## 3. Segredos e criptografia

- Credenciais de terceiro em repouso (token Meta WhatsApp, senha SMTP)
  usam `TextoCriptografado` (Fernet, `app/core/crypto.py`) — transparente
  pro ORM, nunca grava texto puro. Chave real obrigatória em produção
  (`e_ambiente_producao` recusa subir sem `CONFIGURACAO_WHATSAPP_
  ENCRYPTION_KEY` configurada — nunca abre exceção pra segredo vazio).
- Segredos de cron (`X-Cron-Secret`), webhook (assinatura ECDSA do
  SendGrid, HMAC do Mercado Pago/Recall), e API parceiro seguem o
  mesmo padrão: verificação **antes** de tocar no corpo da requisição,
  nunca "confia primeiro, valida depois".
- **Gap conhecido**: rotação de segredo é manual (já documentado em
  memória de sessões anteriores como item resolvido uma vez, mas sem
  automação recorrente).

## 4. Human-in-the-loop como controle de segurança

Vale destacar explicitamente: o approval gate (`Aprovacao`/`Mensagem`,
ver `AI_CURRENT_ARCHITECTURE.md` §3) não é só UX — é o controle que
impede a IA de mandar mensagem comercial pra um terceiro sem revisão
humana. `envio_service.processar_pendentes` só considera
`status="aprovado"` — isso é testado (`tests/integration/test_envios.py`
e correlatos cobrem esse gate). Nenhum dos 8 pontos de uso de IA hoje
despacha conteúdo pra um destinatário externo sem passar por aprovação
OU sem ser, na prática, um texto pra humano copiar manualmente (scripts
de resgate, roteiro de qualificação).

## 5. Prompt injection — risco real, sem defesa estrutural

Ver `AI_CURRENT_ARCHITECTURE.md` §7. O ponto de maior exposição:
`conta_service.enriquecer` injeta HTML/texto de um site institucional
de terceiro direto no prompt, sem isolamento entre "dado recuperado" e
"instrução" — uma página maliciosa poderia tentar instruir a IA via
conteúdo da própria página. Mitigação hoje é só a instrução de "não
inventar", que não é uma defesa contra injeção (é sobre alucinação).
**Recomendação, se for endereçar**: tratar conteúdo de página web
sempre como dado citável, nunca como instrução — mesmo princípio já
aplicado neste projeto (e nas minhas próprias regras de execução) pra
conteúdo observado via ferramentas.

## 6. Rate limiting e disponibilidade

- Rate limit é em memória, por processo (`LimitadorEmMemoria`) — só
  funciona porque hoje roda **uma única instância** Render. Comentário
  no próprio código já avisa: precisaria de Redis compartilhado se
  escalar horizontalmente. Isso é uma limitação de disponibilidade,
  não um vazamento de segurança, mas relevante pro roadmap de
  qualquer coisa que aumente tráfego (ex.: um agente autônomo rodando
  em loop).
- Sem fila/worker (`DATA_FLOW_MAP.md` §8) — um endpoint de cron lento
  bloqueia a requisição HTTP inteira; hoje mitigado só por baixo
  volume por tenant.

## 7. Auditoria como trilha forense

`AuditLog` é imutável (sem update/delete em código), 131 pontos de
escrita cobrindo a maioria das mutações relevantes (`DATA_FLOW_MAP.md`
§7). **Gap**: cobertura depende de disciplina manual — nada impede um
novo call site de mutação de esquecer `auditoria_service.registrar`.

## 8. LGPD

- `RegistroTratamento`, `RegistroSupressaoPermanente`, fluxo de
  titulares com expiração automática via cron diário
  (`/cron/expirar-titulares`).
- Opt-out (`optout_service`) cancela mensagens pendentes em qualquer
  canal e marca supressão permanente — reaproveitado nesta mesma
  sessão pra "excluir contato" no Relatório de Entrega, em vez de
  criar exclusão de decisor isolado nova.
- Exclusão de conta/tenant é deliberadamente restrita (recusa se
  houver negócio/mensagem/reunião vinculada) — decisão de produto já
  tomada, não uma lacuna.

## 9. O que o master prompt pede que ainda não existe (segurança)

- **RAG isolation** (seção 69/88 do master prompt) — não aplicável
  ainda porque não existe RAG nenhum; se for construído, é a coisa que
  mais precisa nascer já testada com o "Critical AI Test" que o
  próprio master prompt descreve na seção 88 (tenant A secreto → IA do
  tenant B pergunta → zero acesso).
- **AI Audit Log dedicado** (seção 73) — hoje a auditoria de ação de
  IA se mistura com auditoria de ação humana no mesmo `AuditLog`; não
  há campo `model`/`tokens_used`/`agent` estruturado.
- **Tool permissions por sensibilidade** (seção 72) — não existe
  "tool" no sentido do master prompt (nenhum agente hoje chama
  ferramentas), então a distinção READ/WRITE/EXTERNAL_ACTION/
  SENSITIVE_ACTION não tem onde se aplicar ainda.

---
Ver `NETWORK_GAP_ANALYSIS.md` para a recomendação de sequenciamento —
qualquer novo agente/orquestrador/RAG deveria nascer já respeitando os
limites descritos aqui, não adicioná-los depois.
