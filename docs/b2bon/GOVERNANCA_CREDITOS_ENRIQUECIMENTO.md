# Governança de créditos, pesquisas e enriquecimento (pesquisa de decisores)

Estado: **implementado e testado localmente; não publicado; nada ativado.** Nenhum valor comercial (franquia, limite, custo por contato, orçamento global) foi inventado: tudo é configuração administrativa e, ausente, **bloqueia**.

## 1. Auditoria (antes de qualquer alteração)

| Achado | Onde | Risco |
|---|---|---|
| A Lusha era chamada sem teto: página de 20 e revelação de **todos** os ids encontrados | `providers/contact_enrichment/lusha.py` | custo sem limite por empresa |
| Erro, timeout e "sem resultados" eram indistinguíveis (`_chamar` devolvia `None` → lista vazia) | idem | cobrança possível tratada como falha; impossível reconciliar |
| A **fila automática** (importação de planilha) chamava `mapear_decisores` e, com ele, a Lusha, sem seleção | `enriquecimento_fila_service.processar_pendentes` | consumo para o universo importado, sem ninguém ter escolhido |
| Limite de contatos era uma **contagem semanal de chamadas** (1 por chamada, independente de quantos contatos a Lusha revelava) | `enriquecimento_limite_service`, `Plano.limite_enriquecimento_contatos_semanal` | não mede crédito; sem ledger; sem reserva |
| Sem orçamento global do provedor, sem reserva, sem idempotência, sem reconciliação | — | gasto acima do contratado |
| Créditos de **IA** já têm carteira, lotes FEFO, reservas, extrato e reconciliação (`contexts/finops`, Fase 15) | `app/contexts/finops/carteira.py` | existente e **não** reaproveitado de propósito (ver §2) |
| Planos são linhas de dados (`plano`), não constantes: os nomes (POC, Free Trial, Starter, Professional, Business, Corporate, Enterprise) vivem no banco de cada ambiente, não no código, e não pude confirmar quais existem em produção | `models/plano.py` | a configuração de enriquecimento fica ligada ao `plano_id` de cada linha existente |
| `get_contact_enrichment_provider`: sem chave em produção → provedor desativado (nada vaza); com chave → Lusha | `api/deps.py` | mantido |

## 2. Decisões de arquitetura

1. **Contabilidade separada por construção.** Tabelas próprias (`enriquecimento_*`, `pesquisa_decisores*`), nenhum lote/movimento/execução compartilhado com IA. Não há conversão nem compensação; teste automático prova os dois sentidos. Alternativa descartada: coluna `categoria` nas tabelas de IA (alteraria tabelas em produção e misturaria saldo).
2. **Unidade: 1 crédito = 1 contato revelado.** É convenção de contagem, não preço. O custo em reais por crédito **não existe no sistema** e a estimativa avisa isso.
3. **Razão append-only** (`enriquecimento_movimento`): saldo, reservado e disponível são **somas** (`delta_saldo`, `delta_reservado`), nunca colunas editáveis. Atualizar/apagar pelo ORM levanta erro; correção é novo lançamento (`ESTORNO`, `AJUSTE`, `RECONCILIACAO`). A exclusão definitiva de tenant (SQL Core) continua funcionando.
4. **Backend é a autoridade.** O cliente envia só `conta_ids`, `decisores_por_empresa` (opcional) e, na confirmação, `selecao_hash` + `idempotency_key`. Campos extras são recusados (422).
5. **Contexto novo** `app/contexts/enriquecimento/` (contrato próprio; só o PREDATOR é chamado, via `predator.contract.registrar_candidatos`). O PREDATOR **não** depende dele.
6. **Provedor pago só pelo caminho governado.** `ContactEnrichmentProvider.pago`; `mapear_decisores` e a fila ignoram provedor pago (ficam só com o QSA gratuito). Teste de AST garante que nada fora dos adaptadores chama `buscar_contatos(` sem governança.

## 3. Universo do ICP ≠ empresas pesquisadas

Criar ICP, gerar lista, importar planilha e enriquecer **nunca** chamam o provedor pago. A pesquisa nasce de uma lista **explícita** de empresas (checkbox em Prospecção → "Pesquisar decisores"). Cada id é conferido contra o tenant (resposta idêntica para "não existe" e "é de outro tenant") e contra o escopo do vendedor. A API não aceita `icp_id`, "todas" ou qualquer atalho de universo.

## 4. Configuração central, versionada e validada

`enriquecimento_config_plano` (por `plano_id`, ou por `tenant_id` quando há condição contratual, que prevalece). Nova versão = nova linha; a anterior ganha `valido_ate`; toda alteração é auditada com motivo.

| Campo | Significado | Obrigatório p/ liberar |
|---|---|---|
| `franquia_creditos` + `periodicidade` (`mensal` renova e vence no fim do mês, sem rollover; `unica` para POC/Free Trial, concedida uma vez) | créditos incluídos | sim |
| `decisores_por_empresa_padrao` / `_max` | padrão exibido e teto | sim |
| `itens_por_lote_max` | empresas por pesquisa | sim |
| `limite_periodo_creditos` | teto extra de consumo+reserva no mês | não (nulo = sem teto além do saldo) |

Validação: inteiros ≥ 0 (mínimo 1 onde faz sentido), padrão ≤ máximo, periodicidade conhecida, exatamente um entre plano e tenant. **Campo obrigatório nulo ⇒ pesquisa bloqueada** com código estável (`plano_sem_configuracao`, `config_incompleta`, `sem_plano_ativo`) e mensagem encaminhando ao comercial. Os planos POC, Free Trial, Starter, Professional, Business, Corporate e Enterprise são configurados nessa mesma tabela, um a um, **pelo comercial**; nenhum número foi pré-carregado. Para Corporate/Enterprise, a condição contratual é uma linha por tenant.

## 5. Decisores por empresa

Seletor no modal (padrão do plano visível e rotulado "padrão do plano" × "escolha sua"). Validação no servidor: inteiro > 0, ≤ máximo do plano, ≤ o que o adaptador do provedor entrega por consulta (`max_contatos_por_consulta`, 20 na Lusha = o tamanho de página que o adaptador já usava), e ainda sujeito a todos os limites totais. Valor inválido é **rejeitado**, nunca ajustado em silêncio. O valor e a origem ficam na pesquisa, na estimativa e na auditoria.

## 6. Estimativa, alternativas e confirmação

`POST /pesquisas-decisores/previa` grava a prévia (nada reservado nem enviado). Ela traz: empresas selecionadas/a consultar/deduplicadas, decisores por empresa e origem, **créditos no máximo**, saldo disponível, limites aplicáveis, bloqueios com código, **alternativas** e **incertezas**. As alternativas (menos decisores por empresa; mais empresas com 1 decisor; menos empresas) usam só limites e saldos conhecidos no momento e vêm com a ressalva "não são promessa; revalidadas"; **nunca mudam a escolha** do usuário (o front só preenche o campo se ele clicar). A prévia vale `ENRIQUECIMENTO_PREVIA_VALIDADE_MIN` minutos.

Confirmação (`POST /pesquisas-decisores/{id}/confirmar`): exige o `selecao_hash` da prévia revista (empresas + decisores + versão da configuração + provedor) e uma `idempotency_key`. O servidor **refaz tudo**: configuração vigente (mudou ⇒ `estimativa_desatualizada`), provedor, decisores já obtidos (mudaram ⇒ nova prévia), limites, saldo, período e orçamento global.

## 7. Validação antes de qualquer chamada ao provedor (10 passos)

1 autenticação/papel; 2 pesquisa do tenant em estado `criada`; 3 seleção explícita revalidada; 4 decisores por empresa; 5 configuração vigente lida do banco (nunca do front); 6 demanda de créditos recalculada; 7 saldo, período, lote e **orçamento global**; 8 deduplicação; 9 **reserva atômica e idempotente**; 10 estado e parâmetros gravados antes de executar. Qualquer falha ⇒ nada chega ao provedor (testado: o provedor simulado registra zero chamadas).

## 8. Razão, reservas e estados

Tipos: `CONCESSAO`, `RENOVACAO`, `RESERVA`, `CONSUMO`, `LIBERACAO`, `ESTORNO`, `EXPIRACAO`, `AJUSTE`, `RECONCILIACAO`. Invariante verificado nos testes após cada fluxo: `saldo = Σ delta_saldo`, `reservado = Σ delta_reservado = Σ reservas das empresas em aberto`, `disponível ≥ 0`.

Pesquisa: `criada → validada → reservada → enviada → (em_processamento) → concluida | parcial | falha | cancelada | reconciliada`. Cada empresa: `pendente, deduplicada, enviado, concluido, sem_resultados, falha, ambiguo, cancelado`. Toda transição fica em `pesquisa_decisores_transicao` (append-only).

Execução (em segundo plano após a confirmação; o front acompanha por GET): a empresa é marcada `enviado` e gravada **antes** da chamada; só quem troca `pendente→enviado` por atualização condicional chama o provedor (duas execuções paralelas nunca enviam a mesma empresa); o consumo e os decisores são gravados na **mesma transação**; falhas seguidas (3) pausam o envio sem martelar o provedor e a pesquisa pode ser retomada (só o que está pendente).

| Desfecho do provedor | Tratamento |
|---|---|
| contatos revelados (≤ limite) | consome só o revelado; libera o resto |
| sem resultados | libera tudo |
| falha **comprovada** antes do consumo (erro de conexão antes do envio, 4xx/429, falha na busca) | libera tudo; empresa `falha` |
| **ambíguo** (timeout de leitura/escrita, 5xx, resposta ilegível, exceção do adaptador, empresa "enviada" sem desfecho há `ENRIQUECIMENTO_ITEM_ENVIADO_STALE_MIN` min) | **não repete e não libera**; reserva retida; pesquisa `em_processamento` com `requer_reconciliacao` |
| provedor devolve acima do limite | cobra até o reservado, registra anomalia e sinaliza reconciliação |

Reconciliação (super_admin): `POST /admin/enriquecimento/pesquisas/{id}/itens/{item}/reconciliar` informa o consumo confirmado no relatório do provedor (0 libera tudo); lança `CONSUMO`/`LIBERACAO`/`RECONCILIACAO` e audita.

## 9. Idempotência, concorrência e retries

Chave por (tenant, operação): `UNIQUE(tenant_id, idempotency_key)` em pesquisa e em movimento; repetir a confirmação devolve o estado atual sem reservar nem chamar de novo; a mesma chave em outra pesquisa é recusada; confirmar uma pesquisa já processada com outra chave é recusado. Reivindicação por atualização condicional (`WHERE estado='criada'`) segura a corrida em qualquer banco; no Postgres, `SELECT … FOR UPDATE` serializa a carteira do tenant e o orçamento global (ordem fixa orçamento → carteira, sem impasse). **Não há retry automático** do envio ao provedor (decisão deliberada: uma repetição às cegas pode cobrar duas vezes); empresa `falha` é terminal e se refaz em nova pesquisa. IDs opacos do provedor e nº de tentativas ficam por empresa.

## 10. Orçamento global do provedor

`enriquecimento_orcamento_global` (por provedor, versionado). **Sem linha vigente com limite ⇒ chamadas bloqueadas** (`orcamento_global_nao_configurado`). O uso é `consumo líquido do mês (todos os tenants) + reservas abertas`; é checado na confirmação sob trava. Nível `alerta` a partir de `alerta_percentual` (log de aviso e destaque no painel administrativo) e `esgotado` bloqueia. Alterar o limite é só por `PUT /admin/enriquecimento/orcamento-global` (super_admin, motivo obrigatório, versão nova, auditoria com limite anterior/novo). **O orçamento global não aparece em nenhuma resposta do tenant.** A reconciliação com o uso informado pelo provedor é manual (relatório do provedor → rota de reconciliação); não há API de uso da Lusha integrada.

## 11. Deduplicação

Na prévia e revalidada na confirmação: (a) mesma empresa duas vezes na seleção (CNPJ, senão domínio); (b) empresa que já tem decisores do mesmo provedor em número ≥ ao pedido; (c) quando falta pouco, só o que falta é pedido (`limite_contatos`). Cada motivo fica no item. A economia **não é garantida** (decisores já obtidos podem não ter os cargos buscados) e a estimativa diz isso. Para o provedor vai o mínimo: nome/domínio/CNPJ da empresa, cargos-alvo e o limite. Respostas do provedor são tratadas como não confiáveis: truncadas ao limite, ids opacos guardados, o corpo bruto nunca é persistido nem logado, a chave nunca sai do adaptador.

## 12. Painel

`GET /pesquisas-decisores/painel` (por tenant): plano e limites, disponível/reservado/saldo, consumido, concedido e expirado no período, pesquisas por estado, estimado × consumido, alertas. `GET /movimentacoes` (extrato com filtros por tipo/pesquisa/data) é restrito a admin/super_admin. Vendedor vê só as próprias pesquisas. `GET /admin/enriquecimento/orcamento-global` (super_admin) mostra o orçamento global e as pesquisas aguardando reconciliação. Tela: `/creditos-enriquecimento`.

## 13. Segurança e privacidade

Autorização no servidor em todas as rotas (sessão + licença + módulo PREDATOR; administração só `super_admin`); posse por tenant em toda consulta; ids de pesquisa são UUID e a resposta a outro tenant é 404 idêntica; limite de requisições por tenant nas rotas de prévia/confirmação; nenhuma credencial de provedor no front, em log ou erro; só ids opacos e contagens no razão; PII dos contatos entra apenas nos decisores do CRM (como já era). Não há callback/webhook do provedor nesta versão (a Lusha é síncrona), logo nada a autenticar nem proteger contra replay.

## 14. Migração e recuperação

`alembic/versions/a4c6e8b0d2f4` (head anterior `f3d5a7c9e1b4`): **só cria 7 tabelas novas e vazias**; nenhuma linha existente é tocada, nenhum saldo é inventado. Dados legados (contagem semanal `enriquecimento_semanal_consumo`, decisores já gravados) ficam intactos. Downgrade remove as 7 tabelas (e o histórico delas) — faça cópia do razão antes de reverter em ambiente com uso. Execução sugerida: staging primeiro (`alembic upgrade head`), conferir `alembic current`, conferir que o CI com PostgreSQL passa, e só então produção, **com autorização**. Recuperação: o razão é reconstruível a partir de `pesquisa_decisores_transicao` + backup do Neon (PITR).

## 15. Observabilidade

Logger `b2bon.enriquecimento`: `ENRIQUECIMENTO_PREVIA`, `_RESERVA`, `_EXECUCAO`, `_PAUSA`, `_ACIMA_DO_LIMITE`, `_EXCECAO`, `_ORCAMENTO_GLOBAL` (alerta/esgotado). Alertas no painel: configuração indisponível, sem saldo, limite do período, pesquisa aguardando reconciliação. Auditoria (`audit_log`): configuração, orçamento, ajuste, estorno, reconciliação.

## 16. Pendências comerciais e de custo (nada foi presumido)

1. **Valores por plano** (franquia, periodicidade, decisores padrão/máximo, empresas por pesquisa, teto no período) para POC, Free Trial, Starter, Professional, Business, Corporate e Enterprise.
2. **Orçamento global mensal da Lusha** e o percentual de alerta.
3. **Custo em reais por crédito/contato** (hoje só em créditos), e se a Lusha cobra a etapa de busca (`prospecting`) ou só a revelação — o adaptador assume que só a revelação cobra.
4. **Regra de excedente** (comprar mais créditos, pós-pago Enterprise): não implementado; sem saldo, a pesquisa é bloqueada.
5. **Planos de faturamento consolidado** (filho usa a licença do pai): hoje cada tenant precisa de licença ativa própria para ter franquia; ficaria bloqueado.
6. **Máximo real de contatos por consulta da Lusha** (o adaptador usa 20 por ser o que já usava).
7. Decidir se o contador semanal legado (`enriquecimento_semanal_consumo`) deve ser aposentado para contatos (hoje não limita mais a pesquisa governada).

## 17. Riscos e limitações

- **Efeito ao promover (decisão do PO antes de qualquer merge):** hoje, em produção, "Mapear decisores" e a fila de enriquecimento trazem contatos da Lusha. Com esta mudança eles passam a trazer **só o QSA** da Receita; os contatos da Lusha só vêm da "Pesquisar decisores", que fica **bloqueada** até existirem (a) a configuração de enriquecimento do plano de cada tenant e (b) o orçamento global do provedor. Ou seja, promover sem configurar = a Lusha para de ser usada. Configure antes (staging primeiro).

- A execução roda em segundo plano **no processo da API** (Render Free dorme/reinicia): empresas ainda pendentes são retomáveis; as "enviadas" sem desfecho viram ambíguas e exigem reconciliação manual — por desenho.
- Se a gravação depois da resposta da Lusha falhar, os créditos foram consumidos no provedor mas não no razão: a empresa fica `enviado` → ambígua → reconciliação.
- SQLite (testes) não trava linhas: a atomicidade por `FOR UPDATE` só é exercida no PostgreSQL (CI/staging). A corrida de confirmação é coberta no SQLite pela atualização condicional e pela unicidade de chaves.
- A expiração da franquia mensal usa uma aproximação favorável ao cliente (o consumo da janela abate a franquia primeiro).
- A reconciliação com o provedor é manual (sem API de uso).
- O contador semanal legado de "contatos" continua existindo para o caminho gratuito (QSA), mas não limita mais a Lusha.

## 18. Testes

`tests/unit/test_lusha_governado.py` (classificação de falhas, limite de revelação) e `tests/integration/test_pesquisa_decisores_governanca.py` cobrem: configuração ausente/incompleta/inválida/versionada/por tenant; seleção explícita e rejeição do universo do ICP; padrão e máximo de decisores; limite por empresa × limites totais; estimativa, incertezas e alternativas sem alterar a escolha; hash/versão/expiração; reserva atômica entre pesquisas e entre tenants; chamada só depois da reserva; idempotência (repetição, outra chave, chave em outra pesquisa, pela API); falha certa, parcial, ambígua, exceção, empresa "enviada" antiga, acima do limite, pausa por falhas seguidas, retomada, cancelamento; reconciliação e estorno; deduplicação; período e orçamento global (somando tenants, só no admin, versionado e auditado); razão append-only; franquia mensal/única e expiração; separação IA × enriquecimento; isolamento de tenant e permissões; painel. Todos com provedor simulado — nenhum orçamento real.
