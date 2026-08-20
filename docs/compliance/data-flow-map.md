# Data Flow Map — B2B ON

Levantamento técnico dos fluxos de dado pessoal na plataforma, primeiro
entregável dos 0–30 dias da [Matriz de Compliance Jurídico-Arquitetural](.)
(GDPR/ePrivacy/AI Act/CLOUD Act/LGPD, versão de trabalho de 2026-08-20).

**Isto não é parecer jurídico.** É um levantamento técnico factual, com
evidência de código (`arquivo:linha`), pra servir de insumo pra revisão
jurídica formal antes do primeiro cliente europeu. Precisa ser recalibrado
sempre que um fluxo novo entrar em produção.

**Legenda de risco** (mesma da matriz): 🟢 controles normais · 🟡 exige
validação contratual/técnica · 🟠 exige TIA/DPIA/LIA · 🔴 não liberar na
EU sem revisão específica.

## 1. Cadastro e autenticação

| | |
|---|---|
| Dado | Nome, e-mail, senha (hash), telefone do vendedor |
| Origem | Formulário de cadastro / painel admin |
| Processamento | Backend B2B ON (`app/services/auth_service.py`) |
| Armazenamento | `Usuario` — Postgres (Neon) |
| Terceiro envolvido | Nenhum |
| Cruza fronteira internacional? | Só se o Neon estiver fora da EU (região a confirmar — ver §8) |
| Risco | 🟢 |

## 2. Prospecção autônoma — descoberta de conta e decisor

| | |
|---|---|
| Dado | CNPJ, razão social, sócios (QSA) — dado de empresa/PJ; nome, cargo, e-mail, telefone, LinkedIn do decisor |
| Origem | Dataset público da Receita Federal (importado em lote), BrasilAPI (consulta pontual de CNPJ, sem chave), **Lusha** (revela e-mail/telefone/LinkedIn do decisor) |
| Processamento | `app/providers/account_data/receita_federal.py`, `app/integrations/brasilapi_client.py`, `app/providers/contact_enrichment/lusha.py` |
| Armazenamento | `Conta`, `Decisor`, `CampoEnriquecido` (com proveniência por campo) — Postgres |
| Terceiro envolvido | Lusha (EUA/Israel — confirmar sede exata e DPA) |
| Cruza fronteira internacional? | **Sim** — nome/e-mail/telefone do decisor sai para a Lusha antes de voltar |
| Risco | 🟠 — LIA (legitimate interest assessment) + Art. 13/14 GDPR (informar titular) + opt-out; ver `Decisor.suprimido_em` já implementado |

## 3. Comunicação com decisor — e-mail

| | |
|---|---|
| Dado | E-mail do destinatário, nome/e-mail do remetente, assunto, corpo completo da mensagem, pixel de rastreio de abertura |
| Origem | Cadência/campanha criada pelo vendedor |
| Processamento | `app/providers/channels/email/sendgrid.py` (produção), fallback SMTP genérico |
| Armazenamento | `Mensagem.conteudo` — Postgres. Evento de entrega/bounce volta via webhook (`/webhooks/sendgrid/eventos`) |
| Terceiro envolvido | SendGrid (Twilio Inc., EUA) |
| Cruza fronteira internacional? | **Sim** |
| Risco | 🟠 — ePrivacy (marketing eletrônico, opt-out), DPA + mecanismo de transferência com SendGrid |

## 4. Comunicação com decisor — WhatsApp

| | |
|---|---|
| Dado | Telefone do destinatário, texto completo da mensagem/template |
| Origem | Cadência/campanha, resposta inbound do lead |
| Processamento | `app/providers/channels/whatsapp/meta.py` |
| Armazenamento | `Mensagem.conteudo` — Postgres. Credencial (`access_token`, `phone_number_id`) por tenant em `ConfiguracaoWhatsApp`, **hoje em texto puro no banco** |
| Terceiro envolvido | Meta Platforms (WhatsApp Business Cloud API) |
| Cruza fronteira internacional? | **Sim** |
| Risco | 🟠 — mapear chain Meta/BSP + subprocessadores; **nota técnica separada**: credencial em texto puro é achado de segurança, não só de compliance — ver observação no fim deste documento |

## 5. Reunião de vídeo + transcrição

| | |
|---|---|
| Dado | Link da reunião, participantes (e-mail), transcrição completa da conversa, resumo gerado por IA |
| Origem | Reunião confirmada com decisor (`Reuniao`) |
| Processamento | Google Calendar API (cria evento/link) → fornecedor de meeting-bot (grava/transcreve) → Anthropic Claude (gera resumo) |
| Armazenamento | `Reuniao.transcricao`, `Reuniao.resumo_ia` — Postgres. Vídeo bruto, se gravado, fica só no lado do fornecedor de meeting-bot, nunca no B2B ON |
| Terceiro envolvido | Google (Calendar), **fornecedor de meeting-bot ainda não contratado** (Recall.ai foi a referência de implementação, mas a integração nunca foi testada contra credencial real), Anthropic (resumo) |
| Cruza fronteira internacional? | **Sim, potencialmente 3x** — dependendo de onde cada fornecedor processa |
| Risco | 🔴 — é o item mais crítico da matriz. Recomendação forte: **exigir fornecedor de meeting-bot com processamento na EU** antes de habilitar pra cliente europeu. Notice + base legal + retenção + criptografia. |

## 6. Billing e pagamento

| | |
|---|---|
| Dado | E-mail do pagador, valor, descrição do plano |
| Origem | Cadastro self-service / renovação de licença |
| Processamento | `app/providers/payment/mercadopago.py` — checkout hospedado pelo Mercado Pago (`init_point`) |
| Armazenamento | `PagamentoLicenca` guarda só IDs externos e status — **nenhum dado de cartão (PAN/CVV) passa ou fica no B2B ON** |
| Terceiro envolvido | Mercado Pago (Mercado Livre, Argentina/Brasil) |
| Cruza fronteira internacional? | Não relevante pra EU (fluxo hoje é Brasil/LatAm) |
| Risco | 🟢 |

## 7. Grafo de relacionamento (visualização)

| | |
|---|---|
| Dado | `tenant_id`, nome/CNPJ da conta, nome/cargo do decisor — **nunca e-mail/telefone** |
| Origem | Espelho automático a partir de `Conta`/`Decisor`/`Mensagem` — nunca é o registro de origem |
| Processamento | `app/graph/client.py` |
| Armazenamento | Neo4j AuraDB Free (região a confirmar — ver §8) |
| Terceiro envolvido | Neo4j Inc. |
| Cruza fronteira internacional? | Depende da região da instância Aura — a confirmar |
| Risco | 🟡 |

## 8. Infraestrutura de dados (onde tudo fica fisicamente)

| Serviço | Função | Região configurada |
|---|---|---|
| Neon (Postgres) | Banco relacional principal — praticamente todos os modelos, incluindo blob de anexos (materiais de oferta, propostas, logo) | **Confirmado em 2026-08-20: `aws-us-east-2` (AWS US East, Ohio, EUA).** Não é EU. Neon não permite trocar região de um projeto existente — migrar pra EU (`aws-eu-central-1` Frankfurt ou `aws-eu-west-2` Londres) exige criar projeto novo e portar os dados. |
| Render | Hospedagem do backend (`b2bon-api`) | **Confirmado em 2026-08-20: Oregon (US West).** Não é EU. Combinado com o DPA (processamento primário sempre nos EUA independente da região), migrar a região do serviço pra EU reduziria latência mas não resolveria sozinho a exposição ao CLOUD Act. |
| Neo4j AuraDB Free | Grafo de relacionamento | **Confirmado em 2026-08-20: Google Cloud, `us-east1` (South Carolina, EUA).** Não é EU. |

**Achado 2026-08-20 — quadro completo confirmado nos 3 painéis**: Neon em `aws-us-east-2` (Ohio), Render em Oregon (US West), Neo4j Aura em Google Cloud `us-east1` (South Carolina). **Nenhum dos três está na Europa hoje.** Isso muda o ponto 2 da conclusão executiva da matriz de "confirmar" para "migrar, se a Frente 4 avançar de fato": Neon exige projeto novo + portada de dados (não troca região in-place); Neo4j Aura, mesma restrição; Render permite trocar a região do serviço nas Settings sem recriar o projeto, mas isso sozinho não resolve o CLOUD Act (DPA confirma processamento primário sempre nos EUA, independente da região do serviço). Sem cliente europeu real confirmado ainda, não há gatilho pra essa migração agora — fica registrado como pré-requisito técnico conhecido, não como próximo passo imediato.

## 9. Fluxos que cruzam fronteira de tenant (por design, não falha)

Todos documentados e propositais, não vazamento acidental:

1. **Rede Social B2B** (`MensagemRedeSocial`) — mensageria intencional entre empresas assinantes, tem `tenant_id_remetente` **e** `tenant_id_destinatario`.
2. **Hierarquia Distribuidor→Revendedor→Cliente** — admin de tenant ancestral gerencia tenants descendentes (`tenant_pai_id`).
3. **Webhook de saída pra Distribuidor** — evento de tenant filho pode ser entregue ao endpoint cadastrado por um tenant ancestral.
4. **Convite Vitrine** — convite de um tenant gera tenant novo, com ligação explícita entre os dois.

## Observações para o pacote documental

- **WhatsApp**: `ConfiguracaoWhatsApp.access_token`/`phone_number_id` ficam em texto puro no Postgres, sem criptografia a nível de coluna. Isso é achado de segurança técnica (não é item da matriz de compliance em si, mas reforça o item 8 "Controles técnicos prioritários" — application-level encryption para conteúdo restrito). Recomendo tratar como item técnico separado, fora deste pacote documental.
- **Sentry**: sem evidência de `SENTRY_DSN` no `render.yaml` — se estiver ativo em produção (memória interna indica que sim, configurado em 2026-08-19), foi setado direto no painel do Render sem passar pelo blueprint versionado. Confirmar e documentar região/retenção de log se ativo.
- **Verificação de e-mail externa (ZeroBounce/Kickbox)**: mencionada em comentário de código mas sem implementação funcional — não é subprocessador ativo hoje, não entra no registro.
