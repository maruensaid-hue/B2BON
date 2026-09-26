# 12 — BID INTELLIGENCE — SELL SIDE (Fase 9, §30–§36)

Contexto: `app/contexts/bids/` (contrato: `contract.py`). API: `/api/v1/bids/*`,
gate **módulo `bids`** (B2B ON Public Sector, §70). UI: **Licitações**
(`/bids`, `/bids/:id`), visível só quando o plano tem o módulo.

Nenhum plano existente ganhou o módulo: o super_admin inclui `"bids"` em
`modulos_contratados` de um plano. Nenhum preço foi criado ou alterado (D-030).

```
Fonte (manual | upload | PNCP*) ──► Licitação (Bid Opportunity §32)
                                     │
      Documento (hash SHA-256, fonte, URL, texto por página)
                                     │  Tender/TR Analyzer (IA C3, via Gateway)
                                     ▼  grounding: trecho literal → página calculada pelo sistema
                           Requisito [sugerido] ──humano──► confirmado | descartado
                                     │
  Cofre (§36) + Offer Intelligence + perfil ──► Matriz de Conformidade (C0)
                                     │
                           Go/No-Go (recomenda, C0) ──► decisão HUMANA (+ justificativa)
                                     │
            Deadline Engine · Competitive Intelligence · Contratos ganhos · Procurement Graph
```
\* PNCP: EXPERIMENTAL, desligado por padrão (`PNCP_HABILITADO`).

## 1. GATE — proveniência de documento

- **Documento**: `sha256` do arquivo, `fonte` (UPLOAD/URL/PNCP), `fonte_url`,
  texto **por página** (`paginas_texto`), download com header `X-Content-SHA256`.
  O mesmo arquivo na mesma licitação não entra duas vezes.
- **Requisito**: `documento_id` + `pagina` + `clausula` + `evidencia` (trecho).
  - A IA devolve categoria, descrição, citação e cláusula. O sistema só grava
    se a citação estiver **literalmente** no texto (normalizado).
  - A **página é calculada** a partir do texto, não aceita da IA.
  - A **cláusula** só é mantida se aparecer na página.
  - Requisito manual que aponta para documento tem de trazer um trecho que
    exista nele (senão 422).
- PDF sem camada de texto: `SEM_TEXTO`, sem análise (não há OCR; TD-059).
- Documento longo: blocos de páginas (40 mil caracteres, até 8 blocos, cada
  um uma chamada medida). Acima disso, `analise_parcial=true`.
- Matriz de conformidade repete a proveniência em `evidencia_edital`
  (documento, hash, fonte, URL, página, cláusula, trecho).

## 2. Compliance Matrix (§34)

TR × portfólio (Offer Intelligence) × certificações/atestados/equipe/parceiros
(cofre) × perfil. Status `COMPLIANT`, `PARTIALLY_COMPLIANT`,
`NON_COMPLIANT`, `UNKNOWN`, `REQUIRES_REVIEW` (regras em
`conformidade.py`). Falta de dado é **UNKNOWN**, nunca "não atende".
Documento que vence antes do prazo da proposta = NON_COMPLIANT com risco.
Ajuste humano exige justificativa e mostra o status calculado ao lado.

## 3. Go/No-Go (§35)

Fatores: Technical Fit, Qualification, Documentation, Commercial Fit,
Margin, Relationship (via `crm.contract`), Competitive Position, Delivery
Capacity, Strategic Fit e Deadline. Cada um FAVORAVEL/ATENCAO/DESFAVORAVEL/
UNKNOWN com motivo. Recomendação GO / NO_GO / INSUFFICIENT_INFORMATION.
**Decisão**: só admin ou o responsável pela licitação; divergir da
recomendação exige justificativa; a recomendação e os fatores ficam gravados
com a decisão (`decisao_go_no_go`).

## 4. Demais capacidades

| Capacidade | Onde |
|---|---|
| Bid Workspace | `GET /bids/licitacoes/{id}/workspace` |
| Document Vault (§36) | `/bids/cofre` (validade, emissor, escopo, hash, alertas ≤30 dias) |
| Deadline Engine | `/bids/prazos`: proposta, esclarecimento, documento que vence antes da proposta, validade do cofre, fim de contrato, prazos do edital (referência com evidência) |
| Competitive Intelligence | `/bids/concorrentes`: só histórico registrado pelo tenant |
| Contract Intelligence | `/bids/contratos` e `/contratos/sinais` (renovação, nova licitação) |
| Procurement Graph foundation | grafo derivado no workspace (PUBLIC_ORGANIZATION → PROCESS → DOCUMENT/LOT/ITEM → BID → RESULT → CONTRACT) |
| Tender ingestion | manual, upload; PNCP (adapter §49, idempotente por fonte + id externo) |

## 5. Fontes (§49)

`GET /bids/fontes` mostra o estado real: MANUAL e UPLOAD disponíveis;
PNCP **EXPERIMENTAL** (implementado a partir do formato público da API,
testado com transporte simulado; o ambiente de desenvolvimento não alcança
pncp.gov.br). Não é apresentado como disponível enquanto não for validado (TD-060).

## 6. Fora do escopo

OCR; embeddings (D-017); lado comprador e barreira Buy/Sell (Fase 10);
preço e empacotamento comercial (Fase 14/OI-015).

## 7. Correção 2026-09-26 — Sell Side em dois segmentos (D-055)

Bid Intelligence cobre **Public Sector Bids** (implementado) e **Enterprise Bids** (RFP/RFI/RFQ
privados, vendor questionnaire): hoje só existe como valor de `modalidade`, com modelo, textos e UI do
setor público (gap G1). Alvo: o mesmo contexto `bids` sobre o núcleo `sourcing`, com workflow
`ENTERPRISE_RFP_SELL` e ruleset `PRIVATE_RFP`. A matriz de conformidade vira a direção SELF do
Evaluation Engine; o analisador de edital/TR vira perfil do Requirement Engine. Go/No-Go e cofre
continuam do `bids`. Plano: `18_STRATEGIC_SOURCING.md` §8 (S1, S7).

## 8. Produto comercial (D-059, OI-019 e OI-015 resolvidos)

- **B2B ON Bid Intelligence**, módulo `bids`: R$ 1.490/mês e 25.000 AI Credits/mês na carteira única do tenant.
- Job-to-be-done: *encontrar, qualificar, analisar e responder oportunidades públicas e privadas*.
- Inclui **Public Sector Bids** e **Enterprise Bids** (RFI, RFP, RFQ, EOI, Private Tender, Vendor Qualification,
  eventos de sourcing recebidos), sem cobrança extra por ser pública ou privada.
- Mesmo engine; a diferença vem de `segment` e `process_type`.
- Estado real de cada capacidade (o que pode ser anunciado): `15_PRICING_AND_ENTITLEMENTS.md` §5.4.
- Plano e página de vendas: OI-021.
