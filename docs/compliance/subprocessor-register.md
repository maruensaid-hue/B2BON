# Subprocessor Register — B2B ON

Terceiro entregável dos 0–30 dias da [Matriz de Compliance Jurídico-Arquitetural](.)
(GDPR/ePrivacy/AI Act/CLOUD Act/LGPD, versão de trabalho de 2026-08-20).
Formato baseado no item "Subprocessor Register" do pacote documental
mínimo da matriz (§6). Consolida [Data Flow Map](./data-flow-map.md) e
[Vendor Inventory](./vendor-inventory.md) num registro por subprocessador,
no formato que normalmente é publicado pra cliente/DPO fazer due diligence.

**Isto não é parecer jurídico** — é a base técnica pra um advogado
formalizar o registro real (que exige confirmação contratual de cada
fornecedor, não só o que o código revela).

| # | Subprocessador | Entidade legal | País de processamento | Finalidade | Categoria de dado | Mecanismo de transferência | Status contratual |
|---|---|---|---|---|---|---|---|
| 1 | Neon | Neon Inc. | EUA (empresa) — banco confirmado em `aws-us-east-2` (Ohio, EUA) em 2026-08-20, **não é EU** | Hospedagem do banco de dados principal | Todo dado pessoal da plataforma | DPF/SCC (conforme DPA da Neon) | DPA público existe, revisão formal pendente |
| 2 | Render | Render Services, Inc. (525 Brannan St, São Francisco, CA 94131, EUA) | EUA — DPA confirma "primary processing operations take place in the United States" independente da região; serviço `b2bon-api` confirmado em Oregon (US West) em 2026-08-20 | Hospedagem da aplicação backend | Dado em trânsito/memória/logs técnicos | Data Privacy Framework; EU SCCs Módulo 2 (Controller→Processor) se o DPF deixar de valer | **Revisado em 2026-08-20** — DPA de 2024-12-19 lido na íntegra. Contato: privacy@render.com. Lista de subprocessadores dinâmica em render.com/trust (não fixa no contrato). Cláusula de government access (§6.6.2): Render tenta redirecionar pedido de autoridade ao cliente antes de divulgar, não divulga voluntariamente |
| 3 | Anthropic | Anthropic PBC | EUA | Processamento de IA (LLM) — resumo, geração de mensagem, qualificação | Nome/cargo de decisor, transcrição de reunião, conteúdo de mensagem | A confirmar | Não revisado |
| 4 | SendGrid | Twilio Inc. | EUA | Envio de e-mail transacional/campanha | E-mail, nome, conteúdo de mensagem | A confirmar | Não revisado |
| 5 | Meta (WhatsApp Business Cloud API) | Meta Platforms, Inc. / Meta Platforms Ireland Ltd. (a confirmar qual entidade se aplica) | EUA/Irlanda | Envio/recebimento de mensagem WhatsApp | Telefone, conteúdo de mensagem | A confirmar | Não revisado |
| 6 | Lusha | A confirmar | A confirmar | Enriquecimento de contato (revela e-mail/telefone/LinkedIn de decisor) | Nome, cargo, e-mail, telefone, LinkedIn | A confirmar | Não revisado |
| 7 | Google | Google LLC / Google Ireland Ltd. (a confirmar qual entidade se aplica) | EUA/Irlanda | Google Calendar — criação de evento/link de reunião | E-mail de participantes | A confirmar | Não revisado |
| 8 | Neo4j (AuraDB) | Neo4j, Inc. | Google Cloud `us-east1`, South Carolina, EUA (confirmado 2026-08-20) | Grafo de relacionamento (espelho de visualização) | Nome/CNPJ de conta, nome/cargo de decisor | A confirmar | Não revisado |
| 9 | Sentry | Functional Software, Inc. | EUA | Observability (captura de exceção/tracing) | Potencial fragmento de payload em stack trace | A confirmar | Status de ativação em produção não confirmado |
| 10 | Mercado Pago | MercadoLibre / Mercado Pago | Argentina/Brasil | Checkout de pagamento | E-mail do pagador, valor — **nunca dado de cartão** | N/A (fluxo Brasil/LatAm, fora do escopo EU por ora) | Não revisado |
| 11 | Fornecedor de meeting-bot (referência: Recall.ai) | A definir | A definir | Gravação/transcrição de reunião de vídeo | Link de reunião, transcrição completa, potencial PII sensível discutido na call | A definir | **Planejado, não contratado** — recomendação da matriz: exigir processamento EU antes de habilitar pra cliente europeu |
| 12 | Brave Search | Brave Software, Inc. | EUA | Descoberta de site institucional | Nome de empresa (não PII de indivíduo) | A confirmar | Não revisado |
| 13 | BrasilAPI | Comunidade open-source, sem entidade formal identificada | Brasil | Consulta pontual de CNPJ | CNPJ (dado de empresa) | N/A (API pública gratuita, sem contrato/DPA) | Sem contrato formal |

## Não classificados como subprocessador

- **Receita Federal (dados abertos)**: dataset público governamental importado em lote, não é chamada de API em runtime a um terceiro contratado.
- **ZeroBounce/Kickbox**: mencionado no código, mas a integração levanta `NotImplementedError` sempre — nenhum dado sai hoje.
- **Endpoint de webhook do Distribuidor** (`url_callback` cadastrado pelo próprio parceiro): não é subprocessador da B2B ON — é infraestrutura controlada pelo cliente/parceiro downstream, que recebe dado de licença/pagamento (não PII de decisor) por decisão dele mesmo.

## Como manter este registro atualizado

Atualizar esta tabela sempre que:
1. Um novo provider real for ativado (nova variável de ambiente com API key preenchida no Render).
2. Um DPA for formalmente revisado/assinado — mudar "Status contratual" pra refletir.
3. A região de processamento de qualquer fornecedor mudar.

Fonte técnica de verdade pra cada linha: `app/providers/**` e
`app/core/config.py` no repositório — qualquer provider real novo
aparece nesses dois lugares primeiro.
