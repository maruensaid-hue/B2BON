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

## Limites desta auditoria (não é cobertura total)

- Backend **sem lock file**: o resultado vale para o que a resolução devolveu hoje, com Python 3.14; a imagem de produção (Python 3.12) pode resolver
  versões diferentes. Mitigação: o workflow agendado abaixo roda `pip-audit .` com Python 3.12. Recomendação (decisão do PO): adotar um lock
  (ex.: `uv lock`/`pip-compile`) — mexe no deploy, por isso não foi feito aqui.
- Não cobre pacotes do sistema operacional da imagem Docker (`python:3.12-slim`) nem o Cloudflare Worker em runtime além das dependências do `package.json`.
- `pip-audit` consulta o banco de avisos do PyPI; vulnerabilidades ainda não publicadas não aparecem.

## Rotina contínua

`.github/workflows/auditoria-dependencias.yml`: roda toda segunda-feira (e sob demanda) `pip-audit .` (Python 3.12) e `npm audit` (Node 20).
**Não bloqueia o CI de cada PR** de propósito: um aviso novo de terceiros não deve travar uma entrega sem relação; vermelho = abrir o relatório do job.
