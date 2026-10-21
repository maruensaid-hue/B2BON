# Governança de créditos, pesquisas e enriquecimento (pesquisa de decisores via Lusha)

Estado (2026-10-21): **implementado, testado e enviado ao staging; nada promovido.** A pesquisa de decisores via Lusha **permanece bloqueada** em qualquer ambiente até existirem (1) configuração de enriquecimento **aprovada** para o plano do cliente, (2) política do provedor (tarifas e preço) **aprovada** e (3) orçamento global do provedor **aprovado**. Nenhum valor comercial foi inventado para destravar nada. Os fluxos de QSA da Receita e de Brasil API **não dependem** dessa configuração e continuam funcionando.

## 0. Condições para sair do staging (status real)

| # | Condição | Status |
|---|---|---|
| 1 | "Mapear decisores" e a fila automática trazem só o QSA da Receita | **Atendida** (função nem recebe provedor de contatos; testes de rota e de fila) |
| 2 | Esses fluxos não chamam Lusha nem a usam como fallback | **Atendida** (QSA vazio = lista vazia; teste de AST proíbe `buscar_contatos(` fora dos adaptadores) |
| 3 | Lusha bloqueada no backend sem configuração aprovada do plano | **Atendida** (`plano_sem_configuracao`, `plano_config_pendente_aprovacao`, `config_incompleta`, `sem_plano_ativo`) |
| 4 | Lusha bloqueada sem orçamento global aprovado e com capacidade | **Atendida** (`orcamento_global_nao_configurado`, `…_pendente_aprovacao`, `…_esgotado`) |
| 5 | Configurações de enriquecimento por plano definidas e aprovadas | **NÃO atendida, de propósito.** Nenhum valor por plano foi informado; nada foi pré-carregado. Lusha segue bloqueada. Ver §16 |
| 6 | Seleção explícita de empresas e confirmação do usuário | **Atendida** (API só aceita `conta_ids`; confirmação ligada ao `selecao_hash`) |
| 7 | Custo-base, markup, contabilização e conciliação documentados e implementados, sem presumir crédito por contato | **Implementada.** Tarifas por ação vêm de política aprovada; consumo debitado é o medido pelo provedor. Regra de arredondamento **de cobrança** e política de ponderação de lotes aguardam aprovação (§7) |
| 8 | Migrações, testes, documentação, observabilidade e recuperação revisados | **Atendida** localmente; PostgreSQL real roda no CI do staging (§14) |
| 9 | Impacto operacional da configuração ausente claro | **Atendida** (§15) |
| 10 | Commit e envio ao staging, sem master | Ver relatório de entrega |

## 1. Auditoria (antes de qualquer alteração)

| Achado | Onde | Risco |
|---|---|---|
| A Lusha era chamada sem teto: página de 20 e revelação de **todos** os ids encontrados | `providers/contact_enrichment/lusha.py` | custo sem limite por empresa |
| Erro, timeout e "sem resultados" eram indistinguíveis (`_chamar` devolvia `None` → lista vazia) | idem | cobrança possível tratada como falha; impossível reconciliar |
| A **fila automática** (importação de planilha) e o botão "Mapear decisores" chamavam a Lusha | `enriquecimento_fila_service`, `mapear_decisores` | consumo sem seleção explícita |
| Limite de contatos era uma contagem semanal de **chamadas** (1 por chamada) | `enriquecimento_limite_service` | não mede crédito; sem razão; sem reserva |
| Sem orçamento global, reserva, idempotência, reconciliação | — | gasto acima do contratado |
| Créditos de **IA** já têm carteira, lotes FEFO, reservas, extrato e reconciliação (`contexts/finops`); a análise de site passa pelo gateway de IA (feature `predator.enriquecimento_site` → workload `website_analysis`, modo `ENFORCE`) | `finops/carteira.py`, `intelligence/registro.py` | existente e **não** reaproveitado de propósito (§2) |
| Planos são linhas do banco, não constantes: POC, Free Trial, Starter, Professional, Business, Corporate e Enterprise vivem no banco de cada ambiente | `models/plano.py` | configuração ligada ao `plano_id` |
| **A documentação oficial da Lusha desmente a premissa "1 contato = 1 crédito"** (ver §6): a busca é cobrada por resultado; e-mail e telefone têm tarifas diferentes (1 e 5); as respostas trazem `billing.creditsCharged` | docs.lusha.com | a primeira versão desta governança presumia 1:1; foi **refeita** para usar o consumo medido |
| `pagination.size` da Lusha aceita **10 a 100**; o adaptador mandava o tamanho do limite (podia ser < 10) | adaptador | requisição inválida |
| `waterfallEnabled` é `true` por padrão quando o recurso está ligado na conta | docs | custo extra de provedores externos não escolhidos |

## 2. Decisões de arquitetura

1. **Contabilidade separada por construção.** Tabelas próprias (`enriquecimento_*`, `pesquisa_decisores*`); nenhum lote, movimento ou execução compartilhado com IA; sem conversão nem compensação (teste prova os dois sentidos). A alternativa de uma coluna `categoria` nas tabelas de IA foi descartada (tocaria tabelas em produção e misturaria saldo).
2. **Quatro grandezas que nunca se misturam:** (a) créditos **do provedor** (medidos pela resposta); (b) créditos de **enriquecimento do cliente** = créditos do provedor × `creditos_cliente_por_credito_provedor` (política aprovada); (c) **custo de aquisição** (lotes de compra); (d) **valor de venda** (custo × (1 + markup)). Ajustes, estornos e reconciliações são lançamentos próprios.
3. **Razão append-only** (`enriquecimento_movimento`): saldo, reservado e disponível são somas; atualizar/apagar pelo ORM levanta erro; correção é novo lançamento. Lotes de compra e transições também são append-only.
4. **Backend é a autoridade**; o cliente envia só `conta_ids`, `decisores_por_empresa` (opcional) e, na confirmação, `selecao_hash` + `idempotency_key`. Campos extras são recusados (422).
5. **Tudo que vale é aprovado:** configuração por plano/tenant, política do provedor e orçamento global nascem **pendentes** e só valem depois de `…/aprovar` (super_admin, auditado). Nada pendente destrava a pesquisa.
6. **Contexto novo** `app/contexts/enriquecimento/` com contrato próprio; o PREDATOR não depende dele para nada além de contabilizar uso por fonte (melhor esforço, em savepoint).

## 3. Fontes de contatos: QSA × Lusha

* `mapear_decisores` e a fila automática: **somente QSA da Receita** (e site/IA no enriquecimento). A função não recebe provedor de contatos; sem CNPJ ou sem QSA o resultado é vazio. Nunca há alternativa para a Lusha.
* Lusha: só pela **pesquisa de decisores** (§5), sobre empresas escolhidas explicitamente.
* O uso de cada fonte (`receita_qsa`, `brasilapi`, `lusha`) é contabilizado por tenant e período (lançamento `USO`, deltas zero). Cobrança por fonte só existirá com regra comercial aprovada.
* Categoria IA: continua no módulo AI Credits (franquia e período validados lá). Uma pesquisa extensa de site respeita a franquia de IA; o universo do ICP não concede franquia nem autoriza chamadas pagas.

## 4. Universo do ICP ≠ empresas selecionadas para a Lusha

Criar/atualizar/enriquecer ICP, gerar lista e importar planilha **nunca** disparam a Lusha. A pesquisa nasce de uma lista **explícita** (checkbox em Prospecção → "Pesquisar decisores"). Cada id é conferido contra o tenant (resposta idêntica para "não existe" e "é de outro tenant") e contra o escopo do vendedor. A API não aceita `icp_id`, "todas" ou qualquer atalho de universo.

## 5. Configuração central versionada, validada, aprovada e auditada

**Por plano** (ou por tenant, para Corporate/Enterprise, prevalecendo): `enriquecimento_config_plano`.

| Campo | Significado | Obrigatório |
|---|---|---|
| `franquia_creditos` + `periodicidade` (`mensal`: renova, vence no fim do mês, sem rollover; `unica`: POC/Free Trial, uma vez) | créditos de enriquecimento incluídos | sim |
| `decisores_por_empresa_padrao` / `_max` | padrão exibido e teto | sim |
| `itens_por_lote_max` | empresas por pesquisa | sim |
| `limite_periodo_creditos` | teto extra de consumo+reserva no mês | não |

**Política do provedor** (`enriquecimento_politica_provedor`, por provedor): `creditos_busca_por_resultado`, `creditos_email`, `creditos_telefone`, `revelar_emails`/`revelar_telefones`, `tamanho_pagina_busca` (10–100 na Lusha), `creditos_cliente_por_credito_provedor`, `markup_percentual`, `metodo_custo` (`lote_referencia` | `media_ponderada`), fotos `custo_unitario_brl` e `preco_unitario_brl` calculadas na publicação, `casas_exibicao`. As tarifas são o que o **provedor publica** (a Lusha informa o preço por ação em `GET /v3/account/usage`; a rota `…/provedores/lusha/tarifas-do-provedor` mostra isso ao administrador para conferência).

**Orçamento global** (`enriquecimento_orcamento_global`): créditos **do provedor** por mês, todos os tenants somados, com `alerta_percentual`.

Validação: inteiros, padrão ≤ máximo, página dentro da faixa do provedor, markup ≥ 0, exatamente um entre plano e tenant. **Qualquer campo obrigatório ausente, versão pendente de aprovação ou política incompleta ⇒ bloqueio com código estável** e mensagem encaminhando ao comercial/administrador. Os 7 planos (POC, Free Trial, Starter, Professional, Business, Corporate, Enterprise) são configurados **um a um** nessa mesma tabela; `GET /admin/enriquecimento/planos` mostra, por plano, se a configuração está aprovada, pendente ou ausente.

## 6. Custo da Lusha: o que a documentação oficial diz e o que o sistema faz

Fontes: [FAQ da API](https://docs.lusha.com/faq/api), [como os créditos são contados](https://docs.lusha.com/user-guide/usage-analytics/how-credits-are-counted), [Enrich Contacts](https://docs.lusha.com/api-reference/enrich/enrich-contacts.md), [Prospecting Contacts](https://docs.lusha.com/api-reference/prospecting/prospecting-contacts.md), [Account Usage](https://docs.lusha.com/api-reference/account/get-account-usage.md).

* A **busca** (`POST /v3/contacts/prospecting`) é cobrada por resultado devolvido (`api_search`) — a taxa não é publicada na página do endpoint; vem de `account/usage` ou do contrato. `pagination.size` aceita 10–100.
* A **revelação** (`POST /v3/contacts/enrich`, 1–100 ids) é cobrada por dado revelado: e-mail 1 crédito, telefone 5 (docs de créditos), cobrando uma vez por contato.
* Ambas as respostas trazem `billing.creditsCharged` (consumo real). 402 = créditos insuficientes (nada processado); 429 = limite de taxa.
* O sistema **não presume** créditos por contato: reserva um **teto** calculado com as tarifas aprovadas (`tamanho_pagina × c_busca + decisores × (c_email + c_telefone)` por empresa) e **debita o `creditsCharged` medido**. Resposta sem medição = desfecho ambíguo (não se cobra estimativa). `waterfallEnabled` é enviado `false`.

## 7. Custo de aquisição, markup, preço e arredondamento

Aporte de referência (informado pelo PO): **R$ 269,94 por 400 créditos Lusha** → custo unitário **R$ 0,67485**; markup aprovado **100%** → preço **R$ 1,3497** por crédito Lusha (≈ **R$ 1,35** na apresentação); margem bruta sobre a venda **50%**.

* Registrado como **lote de compra** (`enriquecimento_lote_compra`: provedor, referência, quantidade, custo total, custo unitário, data, observação), inserido pela migração como histórico. **Não libera nada.** Novos aportes = novos lotes; nada é sobrescrito.
* O preço vigente vem da **política aprovada** (foto do custo e do preço na publicação). Um novo lote **não** muda o preço sozinho: é preciso publicar e aprovar uma nova política. `lote_referencia` usa o custo do lote escolhido; `media_ponderada` usa Σ custo ÷ Σ quantidade de todos os lotes na publicação. **A regra de qual método usar é decisão do PO** (a política exige escolher; não há padrão).
* **Precisão:** `Decimal` em todo cálculo; 8 casas internas (meio-par) só para guardar o custo unitário de um lote. O valor de cobrança (créditos × preço unitário) fica **sem arredondar para centavos** no razão. Só a **exibição** arredonda (2 casas, meio para cima). **A regra de arredondamento da cobrança ainda não foi aprovada** (pendência §16).
* No razão de cada consumo ficam separados: créditos do provedor medidos, créditos do cliente debitados, custo unitário e total, preço unitário e valor de venda. A margem é derivada. Custo, markup e margem **só aparecem para super_admin**.

## 8. Decisores por empresa

Seletor no modal (padrão do plano visível e rotulado). Servidor: inteiro > 0, ≤ máximo do plano, ≤ página da política (e do que o adaptador entrega), e ainda sujeito a todos os limites totais. Valor inválido é **rejeitado**, nunca ajustado em silêncio. Valor, origem (`padrao_plano` | `informado_usuario`) e `selecao_hash` ficam na pesquisa, na estimativa e na auditoria.

## 9. Estimativa, alternativas e confirmação

`POST /pesquisas-decisores/previa` (nada reservado nem enviado). Traz: empresas selecionadas/a consultar/deduplicadas, decisores por empresa e origem, decisores pedidos, **teto de créditos** do provedor e do cliente, **por categoria** (IA 0; Lusha busca; Lusha revelação; QSA e Brasil API sem crédito), saldo disponível, limites, valor máximo estimado em R$ (apresentação), bloqueios com código, **alternativas** e **incertezas** (é um teto, não previsão; busca cobra página inteira; retorno do provedor desconhecido; dedupe sem economia garantida).

Alternativas (menos decisores por empresa; mais empresas com 1 decisor; menos empresas) usam só limites, saldos **e tarifas aprovadas** — incluindo o custo fixo da busca por empresa, que torna "1 decisor em mais contas" menos barato do que parece — com a ressalva "não são promessa". **Nunca mudam a escolha**: o front só preenche o campo se o usuário clicar, e a nova estimativa precisa ser revista de novo.

Confirmação: exige o `selecao_hash` da prévia revista (empresas + decisores + versão da configuração + versão da política + provedor) e uma `idempotency_key`. Mudança de configuração, política, preço, decisores já obtidos ou seleção ⇒ nova prévia (`estimativa_desatualizada`). A prévia expira.

## 10. Validação antes de qualquer chamada ao provedor

1 autenticação/papel e propriedade da pesquisa; 2 estado `criada`; 3 provedor disponível; 4 configuração do plano **aprovada**; 5 política do provedor **aprovada**; 6 orçamento global **aprovado**; 7 seleção explícita revalidada e escopo; 8 decisores por empresa e limites simultâneos; 9 demanda (teto) recalculada com as tarifas; 10 saldo, franquia, lote, período e orçamento global (sob trava); 11 deduplicação; 12 **reserva atômica e idempotente** e estado/parâmetros gravados antes de executar. Qualquer falha ⇒ nada chega ao provedor (testado: o provedor simulado registra zero chamadas).

## 11. Razão, reservas, estados, idempotência

Tipos: `CONCESSAO`, `RENOVACAO`, `RESERVA`, `CONSUMO`, `LIBERACAO`, `ESTORNO`, `EXPIRACAO`, `AJUSTE`, `RECONCILIACAO`, `USO`. Invariantes verificados nos testes: `saldo = Σ delta_saldo`; `reservado = Σ delta_reservado = Σ reservas das empresas em aberto` (cliente e provedor); disponível ≥ 0 salvo consumo real acima do reservado (lançado por inteiro e sinalizado — a realidade não é escondida e o saldo negativo bloqueia novas pesquisas).

Pesquisa: `criada → validada → reservada → enviada → (em_processamento) → concluida | parcial | falha | cancelada | reconciliada`; empresa: `pendente, deduplicada, enviado, concluido, sem_resultados, falha, ambiguo, cancelado`; toda transição em tabela append-only.

Execução em segundo plano após a confirmação (o front acompanha por GET): empresa gravada como `enviado` **antes** da chamada; reivindicação por atualização condicional (duas execuções paralelas nunca enviam a mesma empresa); consumo e decisores na **mesma transação**; 3 falhas seguidas pausam o envio (retomável). `UNIQUE(tenant_id, idempotency_key)` em pesquisa e movimento; repetir a confirmação devolve o estado atual; mesma chave em outra pesquisa é recusada. **Sem retry automático** do envio (repetição às cegas pode cobrar duas vezes).

| Desfecho | Tratamento |
|---|---|
| contatos + `creditsCharged` medido | debita o medido; libera `reservado − medido` |
| sem resultados | debita o que foi medido (a busca pode ter sido cobrada); libera o resto |
| falha **comprovada** (conexão antes do envio, 4xx incl. 402/429) | libera; se a busca já cobrou, debita o medido da busca |
| **ambíguo** (timeout, 5xx, queda, resposta ilegível, exceção, **medição ausente**, empresa "enviada" sem desfecho) | **não repete e não libera**; reserva retida; pesquisa `em_processamento` + `requer_reconciliacao` |
| consumo medido > reservado | lança o consumo real, sinaliza, bloqueia novas pesquisas até regularizar |

## 12. Reconciliação

* **Por pesquisa** (super_admin): `POST /admin/enriquecimento/pesquisas/{id}/itens/{item}/reconciliar` com o consumo **em créditos do provedor** confirmado no relatório dele (0 libera tudo).
* **Com o provedor**: `POST /admin/enriquecimento/provedores/lusha/conciliar` lê `GET /v3/account/usage`, grava a leitura e compara a variação de `credits.used` com os créditos do provedor lançados no razão desde a leitura anterior. **Divergência ≠ 0** ⇒ log `ENRIQUECIMENTO_DIVERGENCIA_PROVEDOR` (erro), destaque no painel administrativo e explicação (pesquisa ambígua pendente? uso fora do B2B ON? virada de ciclo?). **Nada é ajustado automaticamente.** O uso (5 req/min na Lusha) não é consultado por cron nesta versão: é acionado pelo administrador.
* Estorno administrativo informa, se houver, os créditos que o provedor devolveu (`provedor_devolvidos`), que reduzem o consumo do provedor e o orçamento global.

## 13. Orçamento global, deduplicação, segurança e privacidade

* **Orçamento global**: em créditos do provedor, por mês; considera reservas pendentes + consumo medido, checado na confirmação sob trava (orçamento → carteira, ordem fixa). Sem versão **aprovada** com limite ⇒ Lusha bloqueada para todos. Alerta no `alerta_percentual` (log + painel administrativo). Alteração: super_admin, motivo, versão nova, aprovação separada, auditoria com limite anterior/novo. **Nunca aparece na visão do tenant.**
* **Deduplicação**: mesma empresa duas vezes (CNPJ/domínio); empresa que já tem decisores do provedor em número ≥ ao pedido; só o que falta é pedido. Economia **não garantida**. Ao provedor vai o mínimo (nome/domínio/CNPJ, cargos-alvo, limite, página, dados a revelar). Respostas do provedor não são confiáveis: truncadas ao limite, só ids opacos e contagens persistidos; corpo bruto e chave nunca em log, erro ou resposta.
* **Segurança**: autorização no servidor em todas as rotas (sessão + licença + módulo PREDATOR; administração só `super_admin`); posse por tenant em toda consulta; UUID e 404 idêntico para outro tenant; limite de requisições por tenant; sem callback do provedor (a Lusha é síncrona neste fluxo), logo nada a autenticar/replay.

## 14. Migração e recuperação

`alembic/versions/a4c6e8b0d2f4` (head anterior `f3d5a7c9e1b4`): **só cria 10 tabelas novas**; nenhuma linha existente é tocada; nenhum saldo, plano, política ou orçamento é inventado; a única linha inserida é o lote de compra informado (histórico de custo). Testado: upgrade sobre dados anteriores (legado e carteira de IA intactos), downgrade (remove só as 10 tabelas) e novo upgrade. O CI do staging roda `alembic upgrade head` em PostgreSQL limpo e a concorrência da reserva em PostgreSQL real.

Recuperação: downgrade apaga o razão — **copie `enriquecimento_movimento` e `enriquecimento_lote_compra` antes** em ambiente com uso. Em incidente de dados: o razão é reconstruível a partir de `pesquisa_decisores_transicao` + backup do Neon (PITR). Pesquisa travada: estados e ids do provedor ficam por empresa; ambígua ⇒ reconciliar; `enviada` com pendentes ⇒ "retomar". Lusha bloqueada durante migrações enquanto as configurações obrigatórias não forem aprovadas.

## 15. Impacto operacional e observabilidade

**Impacto de promover sem configurar:** "Mapear decisores" e a fila passam a trazer só o QSA; a pesquisa Lusha fica indisponível, com o motivo explicado na tela (modal e painel) até configurar e aprovar plano, política e orçamento global. QSA e Brasil API seguem normalmente.

Logger `b2bon.enriquecimento`: `ENRIQUECIMENTO_PREVIA`, `_RESERVA`, `_EXECUCAO`, `_PAUSA`, `_EXCECAO`, `_ACIMA_DO_RESERVADO`, `_ORCAMENTO_GLOBAL` (alerta/esgotado), `_PROVEDOR_SEM_CREDITOS`, `_DIVERGENCIA_PROVEDOR`, `_FALHA_CONSULTA_USO`. Painel do tenant: bloqueios e seus motivos, saldo, reservado, consumido, expirado, uso por fonte, pesquisas por estado, estimado × consumido, extrato. Painel administrativo (super_admin): orçamento global, política (custo, markup, preço, margem), resultado financeiro, lotes, leituras de uso e divergências, aprovações pendentes, pesquisas a reconciliar. Auditoria (`audit_log`): configuração, política, orçamento, lote, aprovações, ajuste, estorno, reconciliação, conciliação.

## 16. Pendências comerciais e de aprovação (nada foi presumido)

1. **Configuração por plano** (franquia, periodicidade, decisores padrão/máximo, empresas por pesquisa, teto no período) para POC, Free Trial, Starter, Professional, Business, Corporate e Enterprise — **bloqueia a Lusha para cada plano até ser criada e aprovada**.
2. **Política do provedor**: conferir as tarifas (busca por resultado — taxa não publicada nas páginas dos endpoints —, e-mail, telefone), escolher `revelar_emails`/`revelar_telefones`, `tamanho_pagina_busca` e `creditos_cliente_por_credito_provedor` (a proposta natural é 1, mas não foi aprovada), e aprovar o markup de 100% (informado) e o método de custo.
3. **Orçamento global mensal** da Lusha (em créditos do provedor) e percentual de alerta.
4. **Regra de arredondamento da cobrança** ao cliente (hoje: sem arredondar; só a exibição arredonda).
5. **Regra de ponderação de lotes** quando houver mais de um (hoje a política escolhe `lote_referencia` ou `media_ponderada` explicitamente).
6. **Regra de excedente / compra de créditos pelo cliente**: não implementada; sem saldo, a pesquisa é bloqueada.
7. Faturamento consolidado (tenant filho sem licença própria): hoje ficaria bloqueado.
8. Cron de conciliação com o provedor (hoje acionada pelo administrador).

## 17. Riscos e limitações

* Execução em segundo plano no processo da API (Render Free dorme/reinicia): pendentes são retomáveis; "enviadas" sem desfecho viram ambíguas e exigem reconciliação manual — por desenho.
* Se a gravação após a resposta do provedor falhar, o crédito foi consumido lá e não no razão: empresa fica `enviado` → ambígua → reconciliação (e a conciliação com o provedor acusa a diferença).
* Consumo medido acima do reservado deixa o saldo do cliente negativo até regularização (política: não esconder o consumo real).
* SQLite (testes) não trava linhas: a atomicidade `FOR UPDATE` só é exercida em PostgreSQL (CI).
* A taxa da etapa de busca não está nas páginas dos endpoints da Lusha: deve vir de `account/usage` ou do contrato antes de aprovar a política.
* Sem painel de detalhe de pesquisas antigas nem tela de administração de planos/política/lotes: feitos pela API administrativa.

## 18. Testes

`tests/unit/test_enriquecimento_precos.py`, `tests/unit/test_lusha_governado.py`, `tests/test_migracao_enriquecimento.py`, `tests/integration/test_pesquisa_decisores_governanca.py`, `tests/integration/test_enriquecimento_concorrencia_pg.py` (PostgreSQL, CI) e as reescritas dos testes de `mapear_decisores`/fila/listas. Cobrem: configuração e política ausentes/incompletas/pendentes/aprovadas/versionadas; seleção explícita e rejeição do ICP inteiro; padrão e limites de decisores; estimativa com tarifas reais, categorias e incertezas; alternativas sem alterar a escolha; hash/versão/expiração; reserva atômica; chamada só depois da reserva; idempotência; consumo **medido** (e-mail+telefone, busca sem resultado cobrada, falha após busca, medição ausente, acima do reservado, fator do cliente ≠ 1); custo, markup, preço, margem e precisão decimal; lotes append-only e preço que só muda com nova política aprovada; falhas certa/parcial/ambígua/exceção/envio antigo/pausa/retomada/cancelamento; reconciliação por pesquisa e com o provedor (divergência, sem consulta, sem vazar detalhe); deduplicação; período e orçamento global (somando tenants, só no admin, versionado e aprovado); razão append-only; franquia mensal/única/expiração; separação IA × enriquecimento; QSA sem nenhuma configuração; uso por fonte; isolamento de tenant e permissões; painel e motivos de indisponibilidade; migração com dados anteriores, downgrade e novo upgrade. Provedor sempre simulado: nenhuma chamada real, nenhum orçamento real.
