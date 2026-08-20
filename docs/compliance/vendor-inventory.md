# Vendor Inventory — B2B ON

Segundo entregável dos 0–30 dias da [Matriz de Compliance Jurídico-Arquitetural](.)
(GDPR/ePrivacy/AI Act/CLOUD Act/LGPD, versão de trabalho de 2026-08-20).
Complementa o [Data Flow Map](./data-flow-map.md) — aqui o recorte é por
fornecedor, não por fluxo.

**Isto não é parecer jurídico.** Levantamento técnico com evidência de
código; "DPA?" e "País sede" precisam confirmação formal (contrato/site do
fornecedor) antes de virar entregável jurídico.

| Fornecedor | Função na plataforma | Dado que recebe | País sede (a confirmar formalmente) | Status hoje | DPA revisado? |
|---|---|---|---|---|---|
| **Anthropic** (Claude) | Único provedor de LLM — resumo de reunião, geração/personalização de mensagem, qualificação, resumo de site institucional | Nome/cargo do decisor, nome da conta, transcrição de reunião, texto de mensagens já enviadas (via prompt) | EUA | Real, obrigatório em produção | Não |
| **SendGrid** (Twilio) | Envio de e-mail de cadência/campanha, webhook de eventos (bounce/spam) | E-mail do destinatário, nome/e-mail do remetente, assunto, corpo completo | EUA | Real, condicional a chave configurada | Não |
| **SMTP genérico** | Fallback de e-mail se SendGrid não configurado | Mesmo dado do SendGrid | Variável (depende do host contratado) | Real, fallback | N/A |
| **Meta** (WhatsApp Business Cloud API) | Envio/recebimento de mensagem WhatsApp | Telefone do destinatário, texto completo da mensagem | EUA/Irlanda (Meta Platforms Ireland pra usuários EU, a confirmar) | Real, credencial por tenant ou token global | Não |
| **Lusha** | Enriquecimento — revela e-mail/telefone/LinkedIn de decisor | Nome da empresa (saída); nome, cargo, e-mail, telefone, LinkedIn do decisor (entrada) | A confirmar (Lusha tem operação EUA e Israel) | Real, opcional (chave própria) | Não |
| **Mercado Pago** | Checkout Pro — cadastro self-service, renovação de licença | E-mail do pagador, valor, descrição do plano. **Nenhum dado de cartão.** | Argentina/Brasil | Real, condicional a token configurado | Não |
| **Google** (Calendar API) | Consulta disponibilidade, cria evento/link de reunião | E-mail dos participantes, título/descrição do evento | EUA | Real, token global (não por tenant) | Não |
| **Fornecedor de meeting-bot** (referência: Recall.ai) | Grava/transcreve reunião de vídeo | Link da reunião, horário, transcrição completa | A confirmar — **nenhum fornecedor contratado ainda** | **Planejado, não contratado.** Wire format da integração nunca testado contra credencial real | N/A |
| **Brave Search** | Descoberta de site institucional de conta sem domínio cadastrado | Nome da conta (query) — não é PII de pessoa física | EUA | Real, opcional (chave própria) | Não |
| **BrasilAPI** | Consulta pontual de CNPJ complementar | CNPJ (dado de empresa) | Brasil | Real, sem chave, API pública gratuita | N/A (sem contrato) |
| **Receita Federal** (dados abertos) | Snapshot em lote pré-importado — não é chamada de API em runtime | CNPJ, razão social, sócios (QSA) | Brasil | Dataset público governamental já importado, não subprocessador ativo | N/A |
| **Sentry** | Observability — captura de exceção e tracing | Potencialmente fragmento de payload em stack trace | EUA | Ativo? Não confirmável pelo `render.yaml`; memória interna indica configurado em 19/08/2026 — confirmar no painel Render | Não |
| **Neon** | Banco relacional principal (Postgres gerenciado) | Praticamente todo dado pessoal da plataforma | EUA (empresa) **e banco confirmado em `aws-us-east-2`, Ohio — não é EU** (confirmado 2026-08-20) | Real, infraestrutura core | Não — DPA da Neon já existe publicamente (https://neon.com/pdf/DPA.pdf), falta revisão formal |
| **Render** | Hospedagem do backend | Dado em trânsito/memória/logs técnicos | EUA (Render Services, Inc., São Francisco/CA) — serviço confirmado em Oregon (US West) em 2026-08-20 | Real, infraestrutura core | **Sim, revisado em 2026-08-20** — DPA confirma que "primary processing operations take place in the United States" mesmo com região EU selecionada; transferência via Data Privacy Framework, com EU SCCs Módulo 2 (Controller→Processor) como respaldo; segurança: AES em repouso, TLS 1.2+ em trânsito, SOC 2 + ISO 27001; compromisso de redirecionar pedido de autoridade governamental ao cliente antes de divulgar (mitigação de CLOUD Act, §6.6.2 do DPA) |
| **Neo4j** (AuraDB Free) | Grafo de relacionamento (espelho de visualização) | `tenant_id`, nome/CNPJ de conta, nome/cargo de decisor — nunca e-mail/telefone | Google Cloud `us-east1`, South Carolina, EUA (confirmado 2026-08-20) | Real | Não |

## Fornecedores mencionados mas sem dado saindo hoje

- **ZeroBounce/Kickbox** (verificação de e-mail externa): classe existe no código mas levanta `NotImplementedError` sempre que chamada — nenhum dado sai. Não incluir como subprocessador ativo.

## Fluxo a terceiro que não é SaaS da plataforma

- **Webhook de saída pra Distribuidor**: eventos de licença/pagamento entregues via HTTP POST + HMAC pra `url_callback` que o próprio Distribuidor cadastra (ex: ERP/billing interno dele). Não é um vendor da B2B ON — é um endpoint controlado pelo cliente. Vale registrar no Subprocessor Register como "controlado pelo controller downstream", não como subprocessador da plataforma.

## Próximo passo pra fechar este inventário

Confirmar formalmente (contrato ou página de privacidade do fornecedor,
não só o código): país-sede exato de cada linha marcada "a confirmar",
e se cada um já tem DPA/SCC assinado ou aceito via termos de uso padrão.
