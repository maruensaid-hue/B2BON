# SOURCING S0–S2 · Completion Report

- **Data**: 2026-09-26 · **Branch**: `staging`
- **Autorização**: PO, "Autorizado" sobre "S0–S2 são as fases de menor risco para começar" (OI-020).
- **Plano**: `18_STRATEGIC_SOURCING.md` §8. **Sem mudança de schema.** S3–S8 não autorizadas.

## S0 · Performance sem schema

| Gap | Correção | Evidência |
|---|---|---|
| P1: listagens carregavam arquivo e texto de todas as páginas | `conteudo` e `paginas_texto` deferidos em `documento_licitacao`, `documento_compras`, `documento_cofre`; download e análise continuam lendo | `test_sourcing_desempenho.py::test_workspace_da_licitacao_nao_carrega_o_arquivo` |
| P2: sinais de risco com N+1 (e com blobs) | uma consulta de tipos por tenant | `::test_sinais_de_risco_sem_n_mais_1_e_sem_arquivo` (12 processos → 1 consulta de documento; antes 12) |
| P4: listas sem paginação | cursor keyset em `/bids/licitacoes` e `/procurement/{recurso}`, `limite` 1–500 (padrão 100), `X-Proximo-Cursor`; telas com "Carregar mais" (D-056) | `::test_licitacoes_paginadas…`, `::test_cadastros_do_comprador_paginados…` |

Os testes de P1 e P2 foram rodados também contra o código anterior e **falharam**, como esperado.

## S1 · Núcleo `sourcing` sobre as tabelas atuais

| Engine | Onde | Quem usa |
|---|---|---|
| Requirement Engine: um extrator com perfis (`edital_tr`, `documento_compras`; RFP privado testado) | `contexts/sourcing/requisitos.py` | `bids/analise.py`, `procurement/documentos.py` |
| Document Engine: preparação do arquivo, "analisável" (RESTRICTED e sem texto fora da IA) | `contexts/sourcing/documentos.py` | registro e análise dos dois lados |
| Evaluation Engine: regras em ordem, direção SELF/PROPOSAL, UNKNOWN por falta de dado, ajuste humano | `contexts/sourcing/avaliacao.py` | matriz de conformidade (`bids/conformidade.py`) |
| Matching base + estratégia de ICP | `contexts/shared/matching.py` | PREDATOR (`_score_aderencia`) e rede (`calcular_fit_icp`) |

- O núcleo não importa modelo nem contexto de nenhum lado.
- Única mudança de resultado: o fit de ICP da rede passa a casar CNAE pontuado com dígitos. Era um bug, e o PREDATOR já normalizava. A paridade da fórmula está testada em 243 combinações.
- Testes: `tests/unit/test_sourcing_nucleo.py`.

## S2 · Barreira nova

- Protocolo `sourcing/repositorio.py`:
  - `RepositorioVenda` (`bids/repositorio.py`) tem o lado fixo SELL;
  - `RepositorioCompra` (`procurement/repositorio.py`) tem o lado fixo BUY.
- Listas, workspaces e sinais de risco leem pelos repositórios.
- **FinOps** (valor de negócio, custo por licitação) e **Analytics** (renovação de contratos públicos) deixaram de ler as tabelas do vendedor e leem pelo `RepositorioVenda`.
- Nova fitness `tests/unit/test_barreira_sourcing.py`, que roda junto com `test_barreira_buy_sell.py`:
  - tabelas de venda e de compra só no próprio contexto (import e SQL);
  - núcleo neutro;
  - `RepositorioCompra` só no lado comprador;
  - protocolo com lado fixo;
  - ferramentas do agente com o lado de quem as registra.

  Validada com três violações plantadas, todas detectadas.
- `tests/integration/test_sourcing_repositorio.py`: no mesmo tenant com os dois lados, cada repositório só devolve o próprio lado, e tenants diferentes não se veem.

## Validação

| Evidência | Resultado |
|---|---|
| Suíte backend | ✅ **2.015 passed** (+2 skipped: Postgres) |
| Barreira antiga + nova + fronteiras de contexto | ✅ |
| Ruff | 40, sem novos |
| Frontend: lint 25, build | ✅ |
| E2E | ✅ 6/6 |

## Pendências

- TD-081 e TD-085 em andamento: tabelas, contratos, workspaces e as demais estratégias de matching ficam para S3–S5.
- TD-083 (análise assíncrona) na S6.
- OI-019 (empacotamento Enterprise) e S3–S8 aguardam o PO.
