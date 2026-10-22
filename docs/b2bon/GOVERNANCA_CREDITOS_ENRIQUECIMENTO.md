# Governança de créditos, pesquisas e enriquecimento (pesquisa de decisores via Lusha)

Estado (2026-10-21, v5 — decisões comerciais da Lusha já aprovadas, política sincronizada com a Lusha, nota fiscal não bloqueante e estorno manual, §20; v3 — matriz e pacotes, §19): **implementado e testado; destino é o staging; nada promovido.** A pesquisa de decisores via Lusha só roda com (1) configuração de enriquecimento aprovada para o plano do cliente, (2) política do provedor — publicada automaticamente a partir das tarifas que a própria Lusha informa —, (3) custo contratual cadastrado (decisão do PO, já semeada) e (4) orçamento global aprovado (semeado em 6.800 créditos/mês). **Não há validação de contrato nem aprovação adicional a pedir**; o que pode manter a pesquisa fechada é limitação técnica descrita (§20.2): sem credencial da Lusha no ambiente, ou sem a tarifa da busca/e-mail no `pricing` dela. Nenhum valor comercial foi inventado. Os fluxos de QSA da Receita e de Brasil API **não dependem** dessa configuração e continuam funcionando.

## 0. Condições para sair do staging (status real)

| # | Condição | Status |
|---|---|---|
| 1 | "Mapear decisores" e a fila automática trazem só o QSA da Receita | **Atendida** (função nem recebe provedor de contatos; testes de rota e de fila) |
| 2 | Esses fluxos não chamam Lusha nem a usam como fallback | **Atendida** (QSA vazio = lista vazia; teste de AST proíbe `buscar_contatos(` fora dos adaptadores) |
| 3 | Lusha bloqueada no backend sem configuração aprovada do plano | **Atendida** (`plano_sem_configuracao`, `plano_config_pendente_aprovacao`, `config_incompleta`, `sem_plano_ativo`) |
| 4 | Lusha bloqueada sem orçamento global aprovado e com capacidade | **Atendida** (`orcamento_global_nao_configurado`, `…_pendente_aprovacao`, `…_esgotado`) |
| 5 | Configurações de enriquecimento por plano definidas e aprovadas | **Parcial (v3).** A matriz do PO foi carregada (§19) e aprovada em nome dele, mas só nas linhas cujo plano **existe no banco com o mesmo nome**: hoje, "Teste". Starter/Professional/Business/Corporate/POC/Enterprise não existem como planos avulsos (os planos do banco são "PREDATOR Starter" etc.): o administrador liga cada linha ao plano certo (`matriz/aplicar` com `mapeamento`). Nada é adivinhado. Lusha segue bloqueada também pela política e pelo orçamento global. Ver §16 |
| 6 | Seleção explícita de empresas e confirmação do usuário | **Atendida** (API só aceita `conta_ids`; confirmação ligada ao `selecao_hash`) |
| 7 | Custo-base, markup, contabilização e conciliação documentados e implementados, sem presumir crédito por contato | **Implementada.** Tarifas por ação vêm de política aprovada; consumo debitado é o medido pelo provedor. Regra de arredondamento **de cobrança** e política de ponderação de lotes aguardam aprovação (§7) |
| 8 | Migrações, testes, documentação, observabilidade e recuperação revisados | **Atendida** localmente; PostgreSQL real roda no CI do staging (§14) |
| 9 | Impacto operacional da configuração ausente claro | **Atendida** (§15) |
| 10 | Commit e envio ao staging, sem master | Ver relatório de entrega |
| 11 | (v3) Matriz, pacotes, POC e Enterprise implementados e testados; Teste gratuito com 3 decisores | **Atendida** (§19) |
| 12 | (v4) Custo contratual USD 600/mês, 81.600 créditos/ano, câmbio de planejamento R$ 6,00; compra pontual de R$ 269,94 desconsiderada | **Atendida** (§20.1) |
| 13 | (v5) Regras de consumo e cobrança da Lusha | **Atendida por medição, sem aprovação manual.** O débito é o `billing.creditsCharged` de cada resposta; a conciliação lê `GET /v3/account/usage`; as tarifas por ação vêm do `pricing` da própria Lusha (§20.2) |
| 14 | (v5) Nota fiscal e conciliação da venda | **Atendida sem bloquear a venda.** Nem a compra de créditos de IA nem o pagamento de licença emitem nota e não há emissor integrado (OI-025): o checkout segue o mesmo modelo, a nota fica "a emitir" e é emitida quando existir emissor (§20.5) |

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

## 7. Custo, markup, preço e arredondamento

**Base econômica vigente (v4, informada pelo PO; ver §20.1):** USD 600/mês, 81.600 créditos/ano (6.800/mês), câmbio de planejamento R$ 6,00 ⇒ **R$ 0,529411765 por crédito** (USD 0,088235294) e R$ 3.600,00/mês. **A compra pontual de 400 créditos por R$ 269,94 foi desconsiderada** (a migração `b5d7f9a1c3e5` remove o lote semeado, se nenhuma política o referenciar) e não participa de custo, preço, margem nem configuração.

* A política do provedor (`metodo_custo = contrato_mensal`, o método recomendado) tira o custo unitário do custo contratual vigente e guarda uma **foto** dele; um novo câmbio ou contrato só muda o preço com nova política aprovada. `lote_referencia` e `media_ponderada` continuam existindo na API como métodos legados para aportes avulsos, mas nenhum dado de lote alimenta a rentabilidade.
* **Precisão:** `Decimal` em todo cálculo; **12 casas** internas (meio-par) para custo e preço por crédito (o custo contratual é uma dízima); exibição em 9 casas para o custo unitário e 2 para valores em reais (meio para cima). O valor **cobrado** de um pacote é `créditos × preço unitário` em **centavos, meio para cima** (`precos.centavos`, regra do produto), conferido contra o total informado; o consumo por pesquisa no razão fica na precisão interna.
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

`alembic/versions/a4c6e8b0d2f4` (head anterior `f3d5a7c9e1b4`) e, depois dela, `b5d7f9a1c3e5` (v4, §20.7): **só cria 12 tabelas novas** (as 10 da governança + `enriquecimento_pacote` e `enriquecimento_compra`); nenhuma linha existente é tocada; nenhum saldo é inventado. Linhas inseridas, todas informadas pelo PO: o lote de compra (histórico de custo), os 5 pacotes adicionais (aprovados) e a franquia dos planos da matriz que já existem por nome (hoje "Teste"). Testado: upgrade sobre dados anteriores (legado e carteira de IA intactos), downgrade (remove só as 12 tabelas) e novo upgrade. O CI do staging roda `alembic upgrade head` em PostgreSQL limpo e a concorrência da reserva em PostgreSQL real.

Recuperação: downgrade apaga o razão — **copie `enriquecimento_movimento` e `enriquecimento_lote_compra` antes** em ambiente com uso. Em incidente de dados: o razão é reconstruível a partir de `pesquisa_decisores_transicao` + backup do Neon (PITR). Pesquisa travada: estados e ids do provedor ficam por empresa; ambígua ⇒ reconciliar; `enviada` com pendentes ⇒ "retomar". Lusha bloqueada durante migrações enquanto as configurações obrigatórias não forem aprovadas.

## 15. Impacto operacional e observabilidade

**Impacto de promover sem configurar:** "Mapear decisores" e a fila passam a trazer só o QSA; a pesquisa Lusha fica indisponível, com o motivo explicado na tela (modal e painel) até configurar e aprovar plano, política e orçamento global. QSA e Brasil API seguem normalmente.

Logger `b2bon.enriquecimento`: `ENRIQUECIMENTO_PREVIA`, `_RESERVA`, `_EXECUCAO`, `_PAUSA`, `_EXCECAO`, `_ACIMA_DO_RESERVADO`, `_ORCAMENTO_GLOBAL` (alerta/esgotado), `_PROVEDOR_SEM_CREDITOS`, `_DIVERGENCIA_PROVEDOR`, `_FALHA_CONSULTA_USO`. Painel do tenant: bloqueios e seus motivos, saldo, reservado, consumido, expirado, uso por fonte, pesquisas por estado, estimado × consumido, extrato. Painel administrativo (super_admin): orçamento global, política (custo, markup, preço, margem), resultado financeiro, lotes, leituras de uso e divergências, aprovações pendentes, pesquisas a reconciliar. Auditoria (`audit_log`): configuração, política, orçamento, lote, aprovações, ajuste, estorno, reconciliação, conciliação.

## 16. Pendências comerciais e de aprovação (nada foi presumido)

1. **Configuração por plano** (franquia, periodicidade, decisores padrão/máximo, empresas por pesquisa, teto no período) para POC, Free Trial, Starter, Professional, Business, Corporate e Enterprise — **bloqueia a Lusha para cada plano até ser criada e aprovada**.
2. ~~Validação do contrato e aprovação da política~~ — **não são pendências** (decisões já aprovadas pelo PO, §20.2). A política é publicada automaticamente a partir das tarifas que a Lusha informa; se a Lusha não informar a tarifa da busca ou do e-mail, o bloqueio é técnico e descrito (§20.2). Itens históricos desta lista (conferir tarifas, revelar e-mails/telefones, página, fator, markup) viraram regras fixas do §20.2.
3. ~~Orçamento global mensal~~ — semeado em 6.800 créditos/mês (capacidade equivalente a USD 600) pelo PO e aprovado; o percentual de alerta é 80% (alterável).
4. ~~Regra de arredondamento da cobrança~~ — centavos, meio para cima (v3).
5. ~~Ponderação de lotes~~ — substituída pelo custo contratual mensal (v4); lotes são legado.
6. ~~Compra de créditos pelo cliente~~ — **implementada na v3** (§19.3); ~~estorno/chargeback~~ (manual, v4 §20.6) e ~~nota fiscal/conciliação~~ (fluxo v4 §20.5) implementados. Segue pendente: **um emissor fiscal real** (escolha da empresa, credenciais e adaptador) e a compra automática recorrente.
7. Faturamento consolidado (tenant filho sem licença própria): hoje ficaria bloqueado.
8. Cron de conciliação com o provedor (hoje acionada pelo administrador).

## 17. Riscos e limitações

* Execução em segundo plano no processo da API (Render Free dorme/reinicia): pendentes são retomáveis; "enviadas" sem desfecho viram ambíguas e exigem reconciliação manual — por desenho.
* Se a gravação após a resposta do provedor falhar, o crédito foi consumido lá e não no razão: empresa fica `enviado` → ambígua → reconciliação (e a conciliação com o provedor acusa a diferença).
* Consumo medido acima do reservado deixa o saldo do cliente negativo até regularização (política: não esconder o consumo real).
* SQLite (testes) não trava linhas: a atomicidade `FOR UPDATE` só é exercida em PostgreSQL (CI).
* A taxa da etapa de busca não está nas páginas dos endpoints da Lusha: deve vir de `account/usage` ou do contrato antes de aprovar a política.
* Sem painel de detalhe de pesquisas antigas. Política do provedor e orçamento global seguem pela API/tela de orçamento; v3 trouxe telas para matriz, configuração por plano/tenant, pacotes, lotes, POC, compras e auditoria (§19.8).

## 18. Testes

`tests/unit/test_enriquecimento_precos.py`, `tests/unit/test_lusha_governado.py`, `tests/test_migracao_enriquecimento.py`, `tests/integration/test_pesquisa_decisores_governanca.py`, `tests/integration/test_enriquecimento_concorrencia_pg.py` (PostgreSQL, CI) e as reescritas dos testes de `mapear_decisores`/fila/listas. Cobrem: configuração e política ausentes/incompletas/pendentes/aprovadas/versionadas; seleção explícita e rejeição do ICP inteiro; padrão e limites de decisores; estimativa com tarifas reais, categorias e incertezas; alternativas sem alterar a escolha; hash/versão/expiração; reserva atômica; chamada só depois da reserva; idempotência; consumo **medido** (e-mail+telefone, busca sem resultado cobrada, falha após busca, medição ausente, acima do reservado, fator do cliente ≠ 1); custo, markup, preço, margem e precisão decimal; lotes append-only e preço que só muda com nova política aprovada; falhas certa/parcial/ambígua/exceção/envio antigo/pausa/retomada/cancelamento; reconciliação por pesquisa e com o provedor (divergência, sem consulta, sem vazar detalhe); deduplicação; período e orçamento global (somando tenants, só no admin, versionado e aprovado); razão append-only; franquia mensal/única/expiração; separação IA × enriquecimento; QSA sem nenhuma configuração; uso por fonte; isolamento de tenant e permissões; painel e motivos de indisponibilidade; migração com dados anteriores, downgrade e novo upgrade. Provedor sempre simulado: nenhuma chamada real, nenhum orçamento real.

## 19. Matriz de franquias, pacotes adicionais, POC e Enterprise (v3, 2026-10-21)

Fonte: prompt do PO em 2026-10-21. Os números vivem em **um único lugar** (`app/contexts/enriquecimento/matriz_dados.py`), lido pela migração, por `matriz.aplicar` e pela página pública; depois de aplicados viram **linhas versionadas e auditadas** (`aprovado_por = po:matriz-2026-10-21`), e qualquer mudança futura passa por nova versão aprovada.

### 19.1 Matriz (franquia mensal = limite de créditos por pesquisa)

| Linha | Franquia mensal | Créditos por pesquisa | Decisores por empresa (máx.) |
|---|---|---|---|
| POC | sem franquia fixa; **autorização por operação** (§19.5) | teto calculado | **1** |
| Teste gratuito | 30 | 30 | **3** |
| Starter | 30 | 30 | 5 |
| Professional | 60 | 60 | 10 |
| Business | 120 | 120 | 20 |
| Corporate | 180 | 180 | 30 |
| Enterprise | configurável por administrador, por tenant: créditos, empresas, contatos e pesquisas **por período** | idem | idem |

* O limite de decisores é **por empresa, por pesquisa**. O teto de créditos por pesquisa (`limite_creditos_pesquisa`) é validado no servidor na prévia **e** na confirmação (`limite_por_pesquisa`, que vem antes de `saldo_insuficiente` na lista de bloqueios). A matriz **não define padrão** de decisores: o usuário escolhe (§19.6); itens por lote ficam sem limite fixo (só o teto de créditos limita o lote).
* **Teste gratuito = 3.** Não existia valor "5" no repositório (a restrição anterior era a contagem semanal de chamadas, `limite_enriquecimento_contatos_semanal`, outro conceito). Se um ambiente tiver configuração anterior com padrão acima do teto da matriz, `matriz.aplicar` **remove o padrão** (e informa em `ajustes`); o teto da matriz nunca é relaxado.
* **Concessão mensal idempotente**: chave `franquia:AAAA-MM`; reprocessar no mesmo ciclo não duplica. O mês é o **mês-calendário de Brasília** (UTC−3): 31/10 23:59 (BRT) ainda é outubro; 01/11 00:00 (BRT) renova. A rotina `POST /cron/creditos-ia` chama `renovacao.renovar_todos` (concede e expira por tenant, isolando falhas); o painel faz o mesmo sob demanda. A franquia **vence no fim do mês** e o pacote adicional **30 dias depois da confirmação do pagamento (§22)**; nenhum acumula: o que sobrou no balde na hora do vencimento vira `EXPIRACAO` (o consumo é abatido primeiro do que vence antes, ou seja, a franquia antes do adicional) e a nova franquia entra no mês seguinte.
* **Casamento matriz → plano**: por nome exato/apelido (`Teste gratuito` ↔ plano `Teste`). No banco os planos de produto se chamam "PREDATOR Starter/Professional/Enterprise", "CRM …", "MAP …": ligar "Starter" a um deles é decisão comercial e é feita explicitamente (`POST /admin/enriquecimento/matriz/aplicar` com `mapeamento`). Business e Corporate **não existem** como planos hoje; plano não é criado (exigiria preço). `GET /admin/enriquecimento/matriz` mostra a situação de cada linha.

### 19.2 Escopo: o que as franquias limitam e o que não limitam

Limitam **somente** a pesquisa de decisores via Lusha. **Não** limitam: tamanho do ICP (testado com 2.000 empresas), criação/consulta do ICP, geração de listas, "Mapear decisores" e fila (QSA da Receita), Brasil API. A **análise de sites** não consome franquia Lusha (razão de enriquecimento intacto) e usa a franquia de IA (workload `website_analysis`) e o próprio limite semanal do plano. A Lusha nunca é chamada para o ICP inteiro: só para empresas **selecionadas explicitamente** (`conta_ids`; campos extras como `icp_id`/`todas` dão 422).

### 19.3 Pacotes adicionais

| Pacote | Créditos | Preço unitário | Total (exato) |
|---|---|---|---|
| `ENRIQ_400` | 400 | R$ 1,35 | R$ 540,00 |
| `ENRIQ_660` | 660 | R$ 1,28 | R$ 844,80 |
| `ENRIQ_1200` | 1.200 | R$ 1,21 | R$ 1.452,00 |
| `ENRIQ_3000` | 3.000 | R$ 1,08 | R$ 3.240,00 |
| `ENRIQ_ACIMA_3000` | acima de 3.000 | — | **sob negociação**: sem preço, sem checkout automático |

* Catálogo **versionado e aprovado** (`enriquecimento_pacote`): reajuste cria versão **pendente**; a versão aprovada continua valendo até a aprovação; o pedido **congela versão e preço**. `definir_pacote` recusa total ≠ créditos × unitário (centavos) e preço em pacote sob negociação.
* Saldo adicional **separado da franquia** (`origem=compra` no razão, tipo `COMPRA`), **não altera os decisores por empresa**, mas **faz o limite de créditos por pesquisa passar a ser o do pacote enquanto ele vale (§22)**, e **expira 30 dias após a confirmação do pagamento**.
* **Data de expiração informada antes da compra**: o catálogo traz `expira_em_previsto`; a tela mostra "se comprados agora, vencem em DD/MM/AAAA" e a compra **exige** `aceite_expiracao` (sem ele: 422, nada criado). O pedido guarda a data informada.
* Compra: só admin/super_admin; recusada se a pesquisa de decisores estiver indisponível (**não se vende crédito que não pode ser usado**) com os motivos; checkout pelo Mercado Pago existente (referência `enriquecimento:<id>`, valor em centavos). **O crédito só entra pelo webhook assinado** (a volta do navegador não credita). Idempotente (status do pedido, `pagamento_id_externo` único e `compra:<id>` no razão); valor pago ≠ pedido (±R$ 0,01) ⇒ `REJEITADA` e log de erro; pagamento `pending/in_process` ⇒ continua `PENDENTE` até o próximo aviso. A validade são 30 dias contados da **confirmação** do pagamento (o crédito nunca nasce vencido).

### 19.4 Custo, markup e margem (recalculados)

`pacotes.rentabilidade` (`GET /admin/enriquecimento/pacotes/rentabilidade`, só super_admin) calcula, com o custo **contratual** vigente (§20.1; sem ele, o da política aprovada), custo, lucro bruto, markup e margem por pacote, **a cada leitura**. Com R$ 0,529411765 por crédito e relação 1:1: markups de **155% / 142% / 129% / 104%** e margens de **60,8% / 58,6% / 56,2% / 51,0%** sobre o custo nominal de planejamento (testado). (A versão v3 usava o lote pontual de R$ 269,94, desconsiderado.) A relação crédito do cliente × crédito do provedor ainda não foi aprovada; sem ela assume-se 1:1 e a tela avisa (`premissa_fator`). Custo de aquisição, uso medido, créditos do cliente, preço, markup, margem, estornos e reconciliações continuam em campos separados (§2).

### 19.5 POC e Enterprise

* **POC** (`modo=poc_autorizada`, 1 decisor): sem franquia fixa e sem número inventado. `POST /admin/enriquecimento/poc/teto` calcula o teto da operação só com a **política aprovada** (empresas × (busca + decisores × revelação) × fator); sem política aprovada não há teto. `POST …/poc/autorizar` cria a **configuração do tenant PENDENTE** (franquia `unica` = teto, 1 decisor, empresas = lote); só depois de aprovada a operação é liberada. Enquanto isso o plano POC responde `poc_sem_autorizacao`. Uma nova operação de POC no mesmo tenant não ganha franquia sozinha (a concessão `unica` é idempotente): crédito extra é ajuste administrativo com motivo.
* **Enterprise**: configuração do **tenant** (versionada, validada, aprovada, auditada) com `limite_pesquisas_periodo`, `limite_empresas_periodo`, `limite_contatos_periodo` (por mês de Brasília) além de franquia e `limite_periodo_creditos`. Contam só pesquisas confirmadas (prévia e cancelada não contam, nem a própria pesquisa em confirmação); excedente ⇒ `limite_*_periodo`.

### 19.6 Decisores por empresa na tela

Seletor (1 até o máximo do plano). Sem padrão no plano, a escolha é **obrigatória** (o botão de revisar fica desabilitado e o servidor recusa "Informe quantos decisores…"); no POC (máx. 1) já vem selecionado 1. A escolha nunca é alterada em silêncio; as alternativas (profundidade × abrangência) só preenchem o campo se o usuário clicar. A revisão mostra empresas, decisores por empresa, total, saldo, limite por pesquisa, uso no mês (quando há limites por período), alternativas e incertezas; o backend revalida tudo na confirmação.

### 19.7 Bloqueio da Lusha (inalterado)

Em qualquer ambiente, sem **configuração aprovada do plano**, **política do provedor publicada** (agora sincronizada com a Lusha, §20.2), **custo contratual cadastrado** e **orçamento global aprovado e com capacidade**, o backend bloqueia antes de reservar e antes de chamar. Aplicar a matriz **não** libera a Lusha por si só. A compra de pacotes fica bloqueada nesse estado, mas **não** depende de emissão fiscal (§20.5). QSA e site não dependem disso.

### 19.8 Telas, rotas e auditoria

* Tenant: painel (`/creditos-enriquecimento`) com **franquia × adicional, validade**, limites do plano, uso no mês, compra de pacotes (aceite de expiração, histórico) e extrato com `COMPRA`; modal de pesquisa com seletor e limites.
* Site: seção "Créditos de enriquecimento" em `/planos` (rota pública `GET /planos/enriquecimento`: matriz e catálogo; **sem** mensalidade, custo ou margem).
* Super admin: matriz (situação e aplicar com mapeamento), configuração por plano/tenant (criar pendente/aprovar), pacotes e rentabilidade, lotes de compra, POC (teto/autorizar), compras de todos os tenants, **auditoria** (`GET /admin/enriquecimento/auditoria`: eventos `enriquecimento_*`), além do orçamento global e conciliação já existentes.
* Eventos novos: `enriquecimento_pacote_definido/aprovado`, `enriquecimento_compra_iniciada/confirmada` (além dos de configuração, política, orçamento, lote, ajuste, estorno).

### 19.9 Testes da v3

`tests/integration/test_enriquecimento_matriz_pacotes.py` (48 testes): limites por plano (inclui Teste = 3 e a substituição de configuração antiga com 5), concessão mensal idempotente na virada do mês de Brasília, expiração sem acúmulo e consumo parcial, rotina mensal, catálogo e preços exatos, validação de pacote, versão pendente × aprovada, compra (aceite, bloqueio sem Lusha, webhook, repetição, valor divergente, pendente, rejeitada, outras categorias, virada do mês), saldo separado que não muda limites, rentabilidade 50,0/47,3/44,2/37,5, POC (sem autorização, teto, autorização pendente, 1 decisor), Enterprise (limites por período), ICP de 2.000 empresas, site fora da franquia Lusha e com limite próprio, rota pública, painel, webhook assinado do Mercado Pago, permissões de admin e isolamento de tenant. Atualizados `test_migracao_enriquecimento.py` (12 tabelas e dados do PO), `test_pesquisa_decisores_governanca.py` (limite por pesquisa obrigatório) e `test_rotas_publicas_aprovadas.py`.

## 20. Custo contratual, política sincronizada com a Lusha, venda e estorno manual (v5, 2026-10-21)

> **Correção de rumo (v5):** as decisões comerciais da Lusha já foram aprovadas pelo PO (custo, créditos, câmbio de planejamento, preços dos pacotes). Não existe "validação de contrato" nem "aprovação adicional de política" a pedir. A versão v4 havia criado essa etapa; ela foi **removida** (código, API, tela e colunas — migração `c6e8a0b2d4f6`). O que sobra de limitação é **técnica**, descrita onde ocorre.

### 20.1 Base econômica e custo efetivo

Informada pelo PO (nada estimado): **USD 600/mês**; **81.600 créditos/ano** ⇒ referência mensal de **6.800** (anuais ÷ 12, exigido inteiro); custo unitário nominal **USD 0,088235294**; **câmbio de planejamento R$ 6,00** ⇒ **R$ 0,529411765** por crédito e **R$ 3.600,00/mês**. Tabela `enriquecimento_custo_provedor` (versionada e aprovada; `custo.py`), semeada pela migração `b5d7f9a1c3e5` já aprovada. O câmbio de planejamento serve à **precificação**; o custo **contábil** é o pagamento efetivo: `POST /admin/enriquecimento/pagamentos-provedor` registra USD pago, **taxa de câmbio efetivamente aplicada** e **encargos efetivamente cobrados** (informados por quem pagou; sem encargo informado, nenhum é presumido; append-only). A compra pontual de 400 créditos por R$ 269,94 foi **desconsiderada** e removida (a migração apaga o lote semeado se nenhuma política o referencia).

Como o custo mensal é fixo, `custo.custo_efetivo` (e o painel do super admin) informa por ciclo: créditos consumidos (medidos), **ociosos** (que expiram — o sistema nunca presume transferência de saldo entre meses), % de ociosidade e **custo mensal efetivo ÷ créditos realmente consumidos** (pagamentos efetivos quando existirem; senão o de planejamento, com aviso).

### 20.2 Medição, conciliação e política: tudo a partir dos dados da Lusha

* **Medição**: o débito de cada pesquisa é o `billing.creditsCharged` devolvido pela Lusha na busca e na revelação; resposta sem medição é ambígua e nunca é estimada (§6, §11).
* **Tarifas**: `conciliacao.sincronizar_politica` lê `GET /v3/account/usage` e usa o `pricing` informado pela própria Lusha (`api_search`, `revealEmail`, `revealPhone`: `{credits, perQuantity}`), o custo contratual vigente, a **página mínima** que a integração aceita (10), **1 crédito do cliente por crédito do provedor** e o preço de referência = **menor pacote ativo** (R$ 1,35 ⇒ markup ≈ 155%). Publica e **aprova em nome do sistema**; idempotente (se nada mudou, não cria versão; se a Lusha mudar uma tarifa ou o custo mudar, nasce versão nova). A política guarda só o que o provedor **oferece** (e-mail sempre; telefone quando a Lusha informa a tarifa `revealPhone`); **quem escolhe o que revelar é o usuário, em cada pesquisa** (ver §21).
* **Quando roda**: sozinha na estimativa de uma pesquisa (nunca na confirmação/reserva), no agendador (`POST /cron/creditos-ia` ⇒ `conciliacao.rotina`: sincroniza a política e concilia o uso no máximo a cada 6 h; cada etapa falha isolada) e sob demanda (`POST /admin/enriquecimento/provedores/lusha/sincronizar-politica`).
* **Conciliação**: `conciliar` compara a variação de `credits.used` com o consumo lançado no razão; divergência vira alerta; ainda confere `credits.total` informado pela Lusha × créditos anuais do contrato (aviso, não bloqueio).
* **Orçamento global**: semeado em **6.800 créditos/mês** (capacidade equivalente a USD 600), aprovado; nunca passa da capacidade do contrato; considera consumo medido + reservas pendentes sob trava.
* **Bloqueios técnicos reais** (descritos, não escondidos): (1) sem **credencial** da Lusha (`CONTACT_ENRICHMENT_API_KEY`) o provedor fica desativado e nada é consultado — a verificação com a Lusha real não foi possível neste ambiente; todos os testes usam duplo; (2) se `pricing` não trouxer a tarifa da busca ou do e-mail, ou trouxer fração (ex.: 1 crédito por 25 resultados), o modelo de reserva (créditos inteiros por unidade) não consegue montar um teto confiável e a mensagem diz exatamente o que faltou; (3) o `pricing` oficial só documenta `revealEmail`/`revealPhone` em exemplo e cita `api_search` no texto: se a Lusha usar outro nome para a tarifa da busca, a mensagem lista as chaves recebidas.

### 20.3 Preços dos pacotes sobre o novo custo

Os preços definidos pela CyberFort (R$ 1,35 / 1,28 / 1,21 / 1,08 por crédito; totais R$ 540,00 / 844,80 / 1.452,00 / 3.240,00; acima de 3.000 sob negociação) **não mudam**. Sobre o custo nominal de planejamento (R$ 0,529411765) os markups são ≈ **155% / 142% / 129% / 104%** (antes de outros custos).

### 20.4 Reserva global

O orçamento global continua contando **consumo medido + reservas pendentes** sob trava (orçamento → carteira), impedindo estouro por concorrência (teste de concorrência em PostgreSQL no CI).

### 20.5 Venda, nota fiscal e conciliação (mesmo modelo da compra de créditos de IA)

**Auditoria do fluxo de IA** (`finops.compras`): preferência no Mercado Pago, crédito somente pelo webhook assinado e idempotente, sem nota fiscal e sem integração de emissão — e o pagamento de licença também não emite nota (OI-025: "nota fiscal não existe na plataforma"). Logo **não há emissor para reutilizar**; a melhor extensão compatível é a seguinte:

* O **pagamento, o webhook, a assinatura e a idempotência são os mesmos** da compra de IA (referência `enriquecimento:<id>`). O checkout de pacotes **não é bloqueado** por falta de nota.
* Porta opcional `FiscalProvider` (`app/providers/fiscal`): contrato `DadosNota → NotaEmitida`, idempotente por venda, **sem cálculo de tributos** (o emissor aplica as regras da empresa). Hoje só o adaptador desativado existe: a nota fica `SEM_EMISSOR` (nunca simulada) e a venda mostra "nota a emitir". Quando um adaptador real for implementado em `app/providers/fiscal/` e devolvido por `get_fiscal_provider`, a emissão acontece no próximo aviso do pagamento ou pelo botão do administrador.
* **Falha fiscal não desfaz o crédito pago**: nota `FALHA` com o motivo, reemissível sem duplicar.
* **Conciliação em duas dimensões**: a **financeira** (derivada) cruza pedido × valor pago informado × **crédito lançado no razão** × contestação × estorno ⇒ aguardando pagamento · pagamento rejeitado · divergente · contestada · estornada · **conciliada**; a **fiscal** ⇒ nota a emitir · sem emissor · falha · emitida. Tarifas e líquido só entram quando o Mercado Pago os informa (nunca estimados). Equivalente da reconciliação de saldo de IA: `resumo_conciliacao` lista as compras cujo crédito no razão não confere com o pedido.
* Painéis: tenant (histórico com situação e nota) e super admin (`GET /admin/enriquecimento/vendas`).

### 20.6 Contestação e estorno manual

Aviso de **reembolso, chargeback ou cancelamento** do provedor de pagamento sobre compra já aprovada **só sinaliza** (`contestacao_status`, auditoria, log de erro); **não** altera o razão. O estorno de créditos é um **fluxo manual**: o super admin **solicita** (tipo, créditos, justificativa ≥ 10 caracteres e evidência) e **outro** super admin decide (quatro olhos; `ENRIQUECIMENTO_ESTORNO_EXIGE_SEGUNDO_APROVADOR=false` desliga de propósito para equipes de um só administrador). Aprovado, executa um **lançamento compensatório** `ESTORNO_COMPRA` (o crédito original nunca é apagado), limitado ao saldo adicional **ainda não consumido nem vencido**; o que já foi gasto não volta e fica em `creditos_ja_consumidos`. Idempotente (`estorno-compra:<id>`); o vencimento do mês seguinte considera o estorno. Devolver o dinheiro ao cliente acontece fora da plataforma.

### 20.7 Migrações, testes e recuperação

`b5d7f9a1c3e5` (amplia custos/preços para 12 casas; tabelas de custo, pagamentos ao provedor, nota fiscal e estorno; colunas de conciliação na compra; semeia custo e orçamento; remove o lote desconsiderado) e `c6e8a0b2d4f6` (remove as colunas da extinta validação de contrato). Duas migrações, e não edição das anteriores, porque a `a4c6e8b0d2f4` e a `b5d7f9a1c3e5` já podem estar aplicadas no staging. Downgrade remove tabelas/colunas e volta a precisão **sem recriar o lote**; notas, pagamentos ao provedor e estornos são histórico financeiro — copie antes de reverter em ambiente com uso. Testes: `tests/integration/test_enriquecimento_custo_vendas.py` (53), mais ajustes nos demais testes de enriquecimento e migração. Provedores Lusha, pagamento e fiscal sempre simulados.

## 21. Dados a revelar escolhidos pelo usuário em cada pesquisa (v6, 2026-10-22)

No modal "Pesquisar decisores" há duas caixas de seleção: **E-mail** (marcada por padrão) e **Telefone**. O usuário pode pesquisar só o e-mail, só o telefone ou os dois, conforme os créditos que tem — gastar a franquia inteira em uma única empresa ou pesquisar o máximo de decisores só com o e-mail. O **link do perfil no LinkedIn** acompanha todo decisor encontrado, sem crédito extra, quando a Lusha o informa (`socialLinks.linkedin`); a tela mostra, por empresa, quantos decisores vieram com o link.

* **Persistência**: `pesquisa_decisores.revelar_emails` (padrão verdadeiro) e `revelar_telefones` (padrão falso); `pesquisa_decisores_empresa.decisores_com_linkedin`. Migração `d7f9b1c3e5a7`; pesquisas anteriores ficam como "só e-mail", que foi o que de fato revelaram.
* **Teto de reserva**: por empresa, `página × tarifa da busca + decisores × (tarifa do e-mail se marcado + tarifa do telefone se marcado)`, em créditos do provedor × fator. A escolha entra no `selecao_hash`: mudar os dados invalida a prévia e exige nova confirmação.
* **Validação**: ao menos um dado; o telefone só se a política oferecer a tarifa. A confirmação revalida (política que deixou de oferecer o dado ⇒ `estimativa_desatualizada`).
* **Deduplicação por dado**: um decisor já obtido só dispensa a consulta se tiver **todos** os dados pedidos agora. Quem veio de uma pesquisa só de e-mail não conta para uma pesquisa que pede telefone.
* **Execução**: o `reveal` enviado à Lusha é exatamente o escolhido (`emails`, `phones` ou ambos). O consumo cobrado continua sendo o medido pelo provedor.
* **Canal provável do decisor** passa a refletir o dado obtido (e-mail; senão WhatsApp se só há telefone; senão LinkedIn).
* **Limites honestos**: o link do LinkedIn depende de a Lusha devolvê-lo; sem o campo, o decisor fica sem link (nunca inventado). A busca é cobrada por resultado da página mínima (10), de modo que "30 decisores só com e-mail em 30 empresas" só cabe em 30 créditos se a tarifa da busca for compatível; a estimativa mostra o teto antes da confirmação.
* **Testes**: dez casos em `tests/integration/test_pesquisa_decisores_governanca.py` (padrão só e-mail, três combinações, hash, validações, dedupe por dado, LinkedIn, canal, API/painel).

## 22. Super admin sem limites e pacote adicional que define o limite por pesquisa (v7, 2026-10-22)

### 22.1 Pesquisa liberada nos planos da matriz

A migração `e8a0c2d4f6b8` aplica a matriz aprovada (Starter 30/5, Professional 60/10) aos planos de módulo **PREDATOR Starter** e **PREDATOR Professional** (e aos planos da suíte com os nomes `Starter`/`Professional`, se existirem) que ainda **não têm nenhuma configuração**; configuração já definida por administrador nunca é sobrescrita. `matriz.aplicar` passa a tratar todos os planos que casam com a linha (apelidos em `matriz_dados.py`). **Não são criados** planos inexistentes (Business, Corporate, POC exigiriam preço) e **Enterprise** continua configurável por tenant pelo administrador (a matriz não define números para ele). O Lusha só opera onde também houver a credencial do provedor no ambiente.

### 22.2 Super admin

O `super_admin` da plataforma (chave `ENRIQUECIMENTO_SUPER_ADMIN_SEM_LIMITES`, padrão ligada) pesquisa decisores **sem plano, franquia, saldo ou limite**: créditos por pesquisa/período, empresas por pesquisa, pesquisas/empresas/contatos por período. O único teto de decisores por empresa é o que a consulta ao provedor entrega (10). A pesquisa fica registrada com `config_origem=super_admin`; quando o tenant dele não tem saldo, a reserva concede **só o que falta** (`CONCESSAO`, `origem=super_admin`, idempotente por pesquisa) para o razão continuar íntegro, e o consumo continua **medido pela Lusha**. Continuam valendo para ele o provedor disponível, a política de tarifas, o custo contratual e o **orçamento global do provedor** (é a capacidade real contratada, 6.800 créditos/mês, não um limite de plano). Admin, vendedor e usuário comum de qualquer tenant seguem o plano e a franquia.

### 22.3 Pacote adicional e limite por pesquisa

* Enquanto houver **crédito de pacote válido** (não consumido e dentro dos 30 dias), o limite de créditos por pesquisa do tenant passa a ser o **tamanho do pacote** (mais de um pacote ativo: a soma). Ex.: Starter (30) que compra 3.000 passa a poder fazer pesquisa de até 3.000 créditos; quando os 3.000 acabam ou vencem os 30 dias, volta aos 30 da franquia.
* Um pacote **nunca reduz** um limite maior que o plano já dê (Enterprise com limite alto), e plano **sem** limite por pesquisa continua sem limite. **Decisores por empresa, empresas por lote e limites por período não mudam.**
* **Validade**: 30 dias a partir da confirmação do pagamento (não mais o fim do mês); a data aparece antes da compra e o aceite informa isso. A franquia continua vencendo no fim do mês.
* **Baldes** (`ledger.baldes`): o razão é reproduzido cronologicamente; cada concessão vira um balde com validade, cada consumo sai do balde que vence antes (a franquia, depois os pacotes), estorno de pacote reduz o balde e o que sobra no vencimento vira `EXPIRACAO`. Substitui a conta por janela de mês, que não serve para vencimentos no meio do mês. Painel: `composicao.pacotes_ativos`, `adicional_expira_em`, `plano.limite_origem` (`plano` | `pacote` | `super_admin`).
* Migração: nenhuma coluna nova (as compras já guardam `expira_em`); compras anteriores mantêm a validade com que foram creditadas.
* Testes: onze em `tests/integration/test_pesquisa_decisores_governanca.py` (pacote de 3.000, fim do crédito, vencimento aos 30 dias, pacote menor, dois pacotes, painel, super admin sem plano/saldo/limites, demais papéis limitados, orçamento global, painel do super admin), mais os de pacotes/estorno ajustados e o da migração `e8a0c2d4f6b8`.

### 22.4 Business, Corporate e POC (2026-10-22)

* **Business** (120 créditos de franquia mensal, 120 por pesquisa, 20 decisores por empresa) e **Corporate** (180/180/30) já estão na matriz (`matriz_dados.py`) e são **incluídos no valor da contratação do plano**: não há cobrança adicional pela pesquisa dentro desses volumes. No banco de produção esses dois planos ainda **não existem como registro** na tabela `plano` (conferido em 2026-10-22: só POC, Teste, Starter, Professional, Enterprise e os de módulo); criar plano exige preço e limites de usuários que a matriz não define. Quando o super admin cria o plano em Admin → Planos com o nome `Business` ou `Corporate`, a franquia e os limites aprovados são aplicados **na hora** (`matriz.aplicar_ao_plano`); não há passo manual.
* **POC**: 1 decisor por empresa e **até 3 pesquisas no total** (migração `f9b1d3e5a7c9` grava o limite na linha do plano; `poc.autorizar` copia para a autorização do tenant). Como a autorização da POC é única (`periodicidade=unica`), os limites de pesquisas/empresas/contatos contam **na vida do tenant**, não por mês. Continua valendo o orçamento de créditos da autorização, calculado pelas tarifas.

## 23. Relatório de consumo de créditos de IA e de Lusha (v8, 2026-10-22)

Tela **Admin → Consumo de créditos** (`/relatorio-consumo-creditos`) e API `GET /api/v1/relatorio-consumo-creditos` (+ `/csv`, planilha com `;` e BOM para o Excel). Acesso: `admin` e `super_admin`. O super admin vê **todas as empresas**; o admin vê a própria empresa e a subárvore (mesmo escopo de `relatorio_service`); uma empresa fora do escopo responde como inexistente. Período padrão: mês corrente de Brasília; máximo de 366 dias.

Por empresa (tenant) e por usuário, separando as duas carteiras (nunca somadas):

* **Perfil contratado**: plano; IA — franquia mensal; Lusha — franquia, máx. de créditos por pesquisa (e se vem do plano ou de pacote adicional), máx. de decisores por empresa e de empresas por pesquisa; percentual da franquia usado.
* **Consumo**: total, **da franquia** e **adicional** (IA: pacotes comprados, bônus/ajustes e excedente pós-pago com valor; Lusha: pacotes comprados e outros — ajuste, autorização de POC, super admin), expirado no período e saldo atual.
* **Por usuário**: IA — créditos e execuções liquidadas; Lusha — créditos, pesquisas, empresas e decisores das pesquisas que ele confirmou.
* **Aquisições de créditos adicionais**: quantidade, data da confirmação e valor, de IA (`CompraCreditos` aprovadas) e de Lusha (`EnriquecimentoCompra` aprovadas, com a data de validade).

Fontes: o extrato de IA (`movimento_credito` + lotes), `execucao_ia`, o razão de enriquecimento, `pesquisa_decisores` e as compras. Nada é gravado nem recalculado de outro jeito. A origem do consumo de Lusha (franquia × pacote) é derivada do razão por `ledger.baldes(..., coletor=...)`, na ordem em que os créditos vencem; para períodos mais antigos a janela de reprodução é ampliada, e o que não puder ser identificado vai para "outros". Estorno de consumo de IA é abatido do lote que recebeu a devolução. Testes: `tests/integration/test_relatorio_consumo_creditos.py`.
