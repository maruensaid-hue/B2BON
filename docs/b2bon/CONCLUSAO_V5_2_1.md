# Conclusão do Prompt V5.2.1 (2026-10-20)

Estados: **Concluído e validado** · **Implementado, aguardando validação externa** · **Parcial** · **Bloqueado**. Nada foi publicado em produção. Tudo foi enviado ao branch `staging` (autorizado pelo PO; `8254949..6da9b64`). A primeira tentativa de push foi barrada pelo harness da sessão e a segunda passou. **Staging ≠ produção:** o `master` não foi tocado; a promoção continua exigindo autorização explícita.

## A. Resumo executivo

| Fase | Estado |
|---|---|
| 1. Isolamento de tenant rota a rota | **Concluído e validado** (5 falhas comprovadas e corrigidas; riscos residuais documentados) |
| 2. Custos e infraestrutura | **Concluído** como auditoria; 2 otimizações seguras implementadas; valores monetários **não confirmáveis sem painéis** (nenhum inventado) |
| 3. Corpus público de licitações | **Concluído e validado** (SQLite; PostgreSQL só no CI) |
| 4. Alertas do PNCP por ICP | **Concluído e validado**; PNCP e e-mail dos alertas continuam **desligados** |
| 5. PDFs de RI | **Parcial**: backend, segurança, API e testes prontos; **faltam** o painel na tela da conta e a busca automática do PDF no site de RI |
| 6. Provedores de IA | **Bloqueado para uso real** (preparação documentada; nada habilitado) |

Principais riscos achados: webhooks internos públicos que permitiam forjar opt-out/respostas e pausar o canal de e-mail de qualquer tenant; webhook da Meta sem assinatura; licitação/contrato/oferta aceitando referências de outro tenant (e o Go/No-Go lendo a oferta alheia); comentários e mídia de posts públicos e enumeráveis.

## B. Isolamento de tenant

Contagens verificadas por `scripts/qualidade/inventario_rotas.py`: **662 rotas** (587 sessão, 15 chave de API, 60 públicas). Varredura dinâmica: **587 rotas, 1.857 requisições**, ids reais de outro tenant em caminho/query/corpo/busca; 0 vazamentos, 0 alterações, 0 erros 5xx; 225 rotas negadas com 404 usando objetos reais, 203 executadas sem vazamento, 114 negadas por papel, 45 recusadas na validação do corpo (as de objeto têm teste dirigido ou revisão de código). Detalhe e riscos residuais (SQLite no teste, um papel atacante, registro de oportunidade na rede, webhook de e-mail inbound sem assinatura): `AUDITORIA_ISOLAMENTO_TENANT_V5_2_1.md`; matriz: `MATRIZ_ISOLAMENTO_ROTAS.md`.

## C. Custos e infraestrutura

`AUDITORIA_CUSTOS_INFRAESTRUTURA_V5_2_1.md`. Confirmado: repositório público (Actions gratuitos); Render API `free` no `render.yaml`; Redis obrigatório em produção sem declaração no repositório (fornecedor desconhecido); só SendGrid integrado (o "Sender" do prompt não existe no código). Medido: ~26 consultas por tenant por ciclo de 15 min em repouso. Implementado: Sentry sem amostrar crons/health; poda de eventos processados e entregas de webhook. **Não implementado, com razão:** pular tenants ociosos (perderia a detecção de credencial quebrada), storage de objetos (decisão de custo/LGPD do PO), trocar Redis (enfraquece segurança).

## D. Corpus e PNCP

`CORPUS_PUBLICO_LICITACOES.md`, `ALERTAS_LICITACOES.md`. Fato público único por (fonte, id externo), sem `tenant_id`; cópia privada ligada por `corpus_id`; backfill na migração; deduplicação por hash de conteúdo; retificação e situação com eventos próprios. Alertas determinísticos, um por (tenant, edital), entrega por resumo com erro/reprocesso. **Ativação:** depende de UFs e palavras-chave definidas pelo PO, `PNCP_HABILITADO=true`, `ALERTAS_LICITACAO_EMAIL_HABILITADO=true` e merge no `master`.

## E. PDFs de RI

`DOCUMENTOS_RI.md`. Leitura em subprocesso isolado (timeout, memória, páginas, cabeçalho real, criptografia, aviso de conteúdo ativo), fetch por URL pelo caminho anti-SSRF, indicadores com valor/moeda/escala/período/página/trecho/método/confiança/estado, conflito entre documentos, visão unificada site+RI e contexto nos prompts de briefing/estratégia (como dado isolado). 17 testes de integração + migração. **Limitações:** só lê número escrito com moeda ao lado do nome (tabelas sem "R$" ficam de fora), sem OCR, o arquivo não é guardado, sem painel visual, sem busca automática no site de RI.

## F. Provedores de IA

Nenhum habilitado, nenhuma credencial configurada, nenhuma chamada real. Matriz e complemento em `PROVEDORES_IA.md`. Bloqueios: credenciais, avaliação LGPD (região/retenção a confirmar por provedor), decisão de custo.

## G. Evidências técnicas

| Comando | Resultado |
|---|---|
| `python -m pytest -q tests/unit` | 1316 passaram, 1 falha de barreira Buy/Sell **corrigida depois** (reexecutada: 27 testes das regras de arquitetura passam) |
| `python -m pytest -q tests/integration tests/test_migracoes_v5.py tests/test_alembic_upgrade.py tests/test_health.py tests/test_lock_sincronizado.py tests/test_rotas_publicas_aprovadas.py` | **1557 passaram, 18 ignorados** (PostgreSQL ignorado: roda no CI) |
| `python -m ruff check .` | passou |
| `tsc --noEmit`, `npm run build` | passaram (antes da Fase 5, que não alterou o frontend) |
| Navegador (preview local, banco descartável) | página de alertas verificada de ponta a ponta |
| Não executado | `tests/desempenho` (módulo `resource` não existe no Windows), E2E Playwright, PostgreSQL real, imagem Docker |

Commits locais: `d25d861` (V5.2), `9d44d83` (F1-2), `77a05f2` (F3), `a464f89` (F4), `c8effa8` (F5 parcial) e o commit final da Fase 5/6/documentação.

## H. Próximas ações (só o que depende de decisão ou acesso)

1. **Conferir o CI do staging**: ele valida o que só roda lá (PostgreSQL real com as migrações `c9f1`, `d1b3`, `e2c4`, `f3d5`, build da imagem Docker, testes de desempenho). Falha de CI deve ser tratada antes de qualquer promoção ao `master`.
2. Definir UFs e palavras-chave do PNCP por tenant e ligar as chaves (item D).
3. Decidir sobre os provedores de IA adicionais (credenciais, LGPD, custo).
4. Confirmar nos painéis o plano e a fatura de Render, Neon, Sentry, SendGrid e Redis; esclarecer o "Sender".
5. Decidir se o painel de RI na tela da conta e a busca automática do PDF no site de RI entram em uma próxima fase.
6. Avaliar Row-Level Security no Postgres/Neon como segunda camada de isolamento.
