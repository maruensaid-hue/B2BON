# 08 — Segurança alvo (§60–62, §79–80)

> Consolidação da Fase 17 ao final deste documento. Estado e riscos
> anteriores: `SECURITY_BOUNDARIES.md`.

- **Fase responsável**: contínuo; consolidação na 17
- **Estado atual / ponto de partida**: Estado atual e riscos priorizados: `SECURITY_BOUNDARIES.md`.


## Fase 17 — revisão e hardening

| Área | O que foi verificado ou feito | Evidência |
|---|---|---|
| Isolamento tenant × tenant | Varredura de TODAS as rotas GET com ids existentes: nenhum dado privado de outro tenant; controle positivo prova que os ids chegam aos dados; nenhuma resposta 5xx | `test_varredura_isolamento.py` |
| Barreira Buy × Sell | Mesma varredura: dado do comprador nunca aparece fora de `/procurement` | idem, + fitness da Fase 10 |
| Prompt injection | **Achado corrigido**: prompts antigos usavam a tag `CONTEUDO_EXTERNO_NAO_CONFIAVEL` sem neutralizar (site, pergunta de outra empresa podiam fechar o bloco); mensagem de lead ia sem delimitação. Agora neutralizadas/delimitadas; teste ponta a ponta de 5 superfícies | `prompt_seguro.py`, `test_seguranca_ia.py` |
| Isolamento do RAG | Já coberto (Brain por tenant, só itens compartilháveis para fora, procurement fora do Brain) | `test_inteligencia_brain.py`, `test_public_procurement.py` |
| Teto de uso de IA | **Achado corrigido**: 9 rotas com IA sem limite por tenant; fitness function exige limite ou gatilho automático (teto por hora do gateway) | `test_limite_ia_nas_rotas.py` |
| Segredos em log | Tokens em query string mascarados no log do httpx e no erro do sync (Fase 13) | D-043 |
| SSRF | Hosts fixos por conector, sem redirect (Fase 13) | D-042 |
| Dependências | `pip-audit`: 0 vulnerabilidades. `npm audit`: 1 alta em dependência de build (`fast-uri`, via workbox), atualizada só no lockfile → 0 | `frontend/package-lock.json` |
| Segredos padrão | A API se recusa a subir fora de SQLite com `SECRET_KEY`/`JWT_SECRET_KEY` padrão (verificado ao subir o teste de carga) | `config.validar_segredos_de_producao` |
