# PHASE J — pós-plano A–I · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO ("Está autorizado" → "Executar as 3 primeiras questões em sequência"; decisão de usuários do Bid
  Intelligence dada pelo PO na mesma rodada).
- **ADRs**: D-070 (J1), D-071 (J3) · débitos: TD-040, TD-089, TD-092 resolvidos; TD-087 e TD-039 atualizados.

## J1 — Troca de leitura da S6 preparada (desligada)

| Item | Estado |
|---|---|
| Configuração `sourcing_leitura_fonte` | ANTIGA (padrão) · UNIFICADA |
| Leituras trocáveis | vendedor: processos (mesma ordem e keyset), documentos, requisitos, tipos de documento; comprador: tipos de documento |
| Fica nas tabelas antigas | `obter_processo` (registro alterado por quem chama), escrita, processo/documentos do comprador, arquivo e texto (TD-088) |
| Prova | mesma resposta da API nos dois modos após o backfill — SQLite e Postgres 16 (vazios na ordem de cada banco) |
| Efeito em UNIFICADA | sem leitura dupla nessas rotas: workspace do vendedor 26 → 22 consultas, lista 5 → 4, workspace do comprador 19 → 18, riscos 10 → 9 |
| Ativação em produção | **não feita**: portão operacional TD-087/088 (backfill em produção + uma release sem `SOURCING_DIVERGENCIA`) |

## J2 — Débitos técnicos

| Débito | Resultado |
|---|---|
| TD-040 isolamento de decisores | `decisores_da_conta` recebe a conta já validada e filtra pelo tenant dela; teste com decisor intruso e outro tenant |
| TD-089 limiares de risco | ruleset `PUBLIC_PROCUREMENT_BR_14133@2` com os mesmos padrões (3 aditivos, 25%, 50%, 60 dias), os de contrato configuráveis pelo órgão; @1 registrado para o histórico |
| TD-092 duplicação nos conectores | `adapters/interacoes.py` compartilhado (duplicação 43 → 42 blocos) |
| TD-039 aliases | avaliado e mantido: ainda há muitos chamadores; remover não muda comportamento e amplia o risco |

## J3 — OI-023: usuários do Bid Intelligence

| Regra do PO | Implementação |
|---|---|
| R$ 1.490/mês, 25.000 AI Credits, Public + Enterprise Bids | inalterado (D-059) |
| 10 usuários incluídos por tenant | `plano.max_usuarios = 10` (migração `c5e7a9b1d3f4`, só onde estava indefinido); catálogo expõe `usuarios_incluidos` |
| Limite por entitlement, não no código | `PlanLimitsProvider.obter_limite_usuarios` → `Entitlements.limite_usuarios()`; convite e tela de assinatura usam o mesmo |
| Usuários adicionais suportados | `licenca.usuarios_adicionais` (additional_user_quantity); limite = incluídos + adicionais |
| Preço do adicional PENDING_DEFINITION | nenhum valor; página mostra "Usuário adicional: preço em definição" |
| Pool de AI Credits do tenant, não por usuário | testado: 25.000 com 8 usuários a mais e 5 adicionais |
| Supplier Guest / externo não conta | `PAPEIS_EXTERNOS` fora da contagem; o Supplier Guest segue sem usuário (link) |
| OI-023 | RESOLVED (D-071) |

Não antecipado: tela de Admin para editar usuários adicionais e cobrança deles (preço pendente); preço do buyer seat
adicional do Strategic Sourcing segue OI-022.

## Code size guard (§34)

| Métrica | Valor |
|---|---|
| Arquivos adicionados | 3 de aplicação (`sourcing/leitura.py`, `adapters/interacoes.py`, migração `c5e7a9b1d3f4`) + 4 de teste |
| LOC da aplicação | +314 / −74 |
| LOC de testes | +283 / −11 |
| Duplicação | 43 → **42** blocos (~1.889 → ~1.877 linhas) |

## Validação

| Evidência | Resultado |
|---|---|
| Suíte completa | ✅ **2.094 passed** (+9 skipped: 8 Postgres, 1 medição) |
| Postgres 16 | ✅ `PG_MIGRACOES_OK c5e7a9b1d3f4`; 8/8 (inclui J1) |
| E2E | ✅ 12/12 (página de vendas mostra 10 usuários e o adicional sem preço) |
| Ruff 40 · oxlint 25 · build | ✅ sem novos |
