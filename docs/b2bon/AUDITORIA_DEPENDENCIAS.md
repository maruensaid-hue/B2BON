# Auditoria de dependências (2026-10-20)

## Escopo: todos os manifestos do repositório

| Conjunto | Manifesto | Lock | Runtime | Ferramenta |
|---|---|---|---|---|
| Backend Python | `pyproject.toml` | **não existe** (versões resolvidas na instalação) | Python 3.12 (Docker); CI em 3.11 | `pip-audit` |
| Frontend / Worker | `frontend/package.json` | `frontend/package-lock.json` | Node 20 (CI) | `npm audit` |

Não há outros `package.json`/`requirements*.txt` no repositório (as cópias em `.claude/worktrees/` são espaços de trabalho de agentes, fora do produto).

## Comandos e resultados

| Comando | Resultado antes | Ação | Resultado depois |
|---|---|---|---|
| `python -m pip_audit .` (resolve as dependências do `pyproject.toml`; 58 pacotes, Python 3.14 local) | **0 vulnerabilidades conhecidas** | nenhuma | — |
| `npm audit` em `frontend/` (495 pacotes: 49 prod, 446 dev) | **2 altas**, ambas transitivas e só de build | `npm audit fix` (**sem** `--force`): lock atualizado `brace-expansion 2.1.4→2.1.7 / 5.0.9→5.0.12`, `source-map-js 1.2.1→1.2.2` | `npm audit`: **0 vulnerabilidades**; `npm run build` OK; `npm run lint` com os mesmos 25 avisos de antes |
| `npm audit --omit=dev` | 0 (nada de produção em runtime) | — | — |

Detalhe das duas altas corrigidas (nenhuma tocava código em produção; ficam no pipeline de build/PWA):

- `brace-expansion` (transitiva de `minimatch` ← `glob`/`filelist` ← `workbox-build`/`vite-plugin-pwa`): negação de serviço por expansão quadrática
  e por recursão (GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p). Correção compatível publicada.
- `source-map-js` (transitiva de `postcss` ← `vite`/`@tailwindcss`): DoS do event loop por offsets de seção de source-map (GHSA-68fv-2mgg-jv7q). Idem.

## Classificação

- **Corrigidas**: as 2 do frontend. **Não corrigidas**: nenhuma. **Mitigadas / não aplicáveis**: as 2 eram só de build (não chegam ao runtime do usuário).

## Lock do backend (adotado em 2026-10-20, decisão do PO)

O backend passou a ter `requirements.lock` e `requirements-dev.lock` (resolução universal com hashes, gerada com `uv pip compile --universal`). A imagem Docker, o CI e os
jobs agendados instalam o lock (`pip install --require-hashes -r ...`, depois `pip install --no-deps -e .`). Validação para o Python 3.12 de produção: (1) simulação
de instalação `uv pip sync --dry-run --python-version 3.12 --python-platform x86_64-manylinux_2_28` (e 3.11, arm64) confirma wheel e hash de cada pacote; (2) suíte inteira
(1209 unitários + 1383 de integração) passou num ambiente instalado do lock; (3) `pip-audit -r requirements.lock --require-hashes`: 0 vulnerabilidades. **Não foi possível
construir a imagem Docker localmente** (Docker Desktop desligado); o build real acontece no deploy do staging.

**Atenção — o lock fixa versões mais novas que as do ambiente de desenvolvimento** (ex.: SQLAlchemy 2.1.5 contra 2.0.51, Pydantic 2.14.1 contra 2.13.4, FastAPI 0.153 contra
0.141): é o que um build novo da imagem resolveria (o `pyproject.toml` não tinha teto de versão), agora fixo e testado. A camada de dependências do Render só é refeita quando o lock
muda. `tests/test_lock_sincronizado.py` impede o lock de ficar para trás do `pyproject.toml`.

## Limites desta auditoria (não é cobertura total)

- (resolvido) O backend não tinha lock; agora tem — ver a seção acima. Resta o limite de que a auditoria cobre as dependências Python, não o sistema operacional da imagem.
- Não cobre pacotes do sistema operacional da imagem Docker (`python:3.12-slim`) nem o Cloudflare Worker em runtime além das dependências do `package.json`.
- `pip-audit` consulta o banco de avisos do PyPI; vulnerabilidades ainda não publicadas não aparecem.

## Rotina contínua

`.github/workflows/auditoria-dependencias.yml`: roda toda segunda-feira (e sob demanda) `pip-audit -r requirements.lock` (o que a produção instala), `pip-audit .` (o que um lock novo resolveria hoje) e `npm audit` (Node 20).
**Não bloqueia o CI de cada PR** de propósito: um aviso novo de terceiros não deve travar uma entrega sem relação; vermelho = abrir o relatório do job.
