# Enrichment Resource Manager — auditoria e verificação de fornecedores (Etapa 1)

Estado em 2026-11-09: **só auditoria e verificação; nenhum código foi alterado.** Origem: master prompt do PO (franquia unificada de pesquisa de decisores + orquestração de recursos gratuitos antes da Lusha).

## 1. O que já existe (mapa da arquitetura atual)

| Peça | Onde | Observação |
|---|---|---|
| Pesquisa de decisores governada (seleção explícita → prévia → confirmação → reserva → execução → liquidação) | `app/contexts/enriquecimento/` (`pesquisa`, `execucao`, `ledger`, `config`, `matriz`, `pacotes`, `custo`, `conciliacao`, `painel`) | Fluxo completo e testado; é o único que chama o provedor pago |
| Provedor pago (Lusha) atrás de nome genérico `contatos` | `app/providers/contact_enrichment/contatos_b2b.py` (+ `base.py`, `stub.py`, `desativado.py`) | Porta `ContactEnrichmentProvider`; estados `ok/sem_resultados/erro_seguro/ambiguo`; consumo MEDIDO (`billing.creditsCharged`) |
| Razão de créditos append-only, reserva, expiração, pacotes, estorno, reconciliação | `ledger.py`, `pacotes.py`, `estornos.py`, tabelas `enriquecimento_*` | Isolado dos AI Credits por construção |
| Franquia por plano (matriz) | `matriz_dados.py`, `enriquecimento_config_plano` | Teste 30, Starter 30, Professional 60, Business 120, Corporate 180 créditos/mês; POC 1 decisor, 3 pesquisas |
| QSA da Receita + Brasil API | `conta_service.mapear_decisores`, fila de enriquecimento | **Gratuitos e fora da franquia hoje** (decisão D-094: "cobrança por fonte só existirá com regra comercial aprovada") |
| Pessoas nomeadas no site (regras determinísticas, sem IA) | `app/contexts/predator/pessoas_site.py`, `prospeccao.py` | Gratuito, fora da franquia |
| Importação de conexões do LinkedIn (CSV) | D-102 | Gratuito, fora da franquia |
| Identidade e deduplicação do decisor | `prospeccao.registrar_candidatos` | **Por nome normalizado dentro da conta.** Não existe id global, nem proveniência/confiança/validade por campo (só `Decisor.origem` e `email_status`) |
| Painel administrativo | `painel.visao_administrativa`, Admin → Consumo de créditos | Mede só a Lusha (orçamento, política, resultado financeiro); não mede fontes gratuitas |
| Isolamento | RLS em produção desde 2026-10-29 (D-110 a D-112) | Qualquer tabela nova com dado pessoal precisa entrar na política |
| "Harvey" | Repositório de referência clonado (MIT, nunca executado); seus recursos foram adaptados ao PREDATOR (sinais, pessoas do site, descoberta) | Não é um fornecedor externo chamado em tempo de execução |

Produção (31/10): 291 decisores vieram da Lusha (origem `contatos`), 1.190 do QSA, 7.947 do LinkedIn; o restante veio de importação de planilha.

## 2. Fornecedores gratuitos: o que a documentação oficial confirma

Verificado em 2026-11-09 nas páginas oficiais. **Nenhuma chamada real foi feita** (não há chaves) e nenhuma integração foi criada.

| Fornecedor | API no plano gratuito | Franquia gratuita | Conclusão |
|---|---|---|---|
| Hunter | **Sim**, segundo a central de ajuda oficial | 50 créditos/mês (Email Finder, Domain Search, Verifier); Domain Search limitado a 10 resultados por consulta no gratuito; limites 15 req/s e 500 req/min | Único com API gratuita comprovada. Devolve nome, cargo, senioridade, departamento, `decision_maker`, LinkedIn, telefone e verificação. Termos: sem regra expressa sobre revenda/armazenamento, mas vedam "serviço concorrente" sem consentimento — **uso em SaaS multi-cliente precisa de confirmação do fornecedor** |
| Prospeo | **Não** (a central de ajuda oficial diz que API e processamento em lote não estão no gratuito) | ~100 créditos/mês (as fontes divergem) | API só a partir de plano pago (Starter, cerca de US$ 37–49/usuário/mês): **exige autorização de gasto** |
| Snov.io | **Não** (página oficial: "API & webhooks access and export are not available in Trial") | 50 créditos/mês | Inutilizável por API no gratuito |
| Apollo | **Incerto.** Oficial: "acesso básico à API para todos"; relato de usuário: People Search devolve `API_INACCESSIBLE` no gratuito; a página oficial diz que API avançada fica em planos Custom | Valor não publicado; Enrichment custa 1–9 créditos por pessoa | Só um teste com chave real resolve; termos de uso comercial não verificados |
| OpenEnrich | **Não localizado** em nenhuma fonte pública | — | Não dá para avaliar licença, API nem uso; não integrar sem o endereço oficial do projeto |

**Capacidade gratuita verificável hoje:** cerca de **50 créditos/mês (Hunter)**. O orçamento mensal da Lusha é de 6.800 créditos. Os fornecedores gratuitos, sozinhos, cobrem menos de 1% dessa demanda. A economia relevante vem de cache, deduplicação, das fontes gratuitas que o sistema já tem (QSA, site, LinkedIn) e de não chamar a Lusha quando elas bastam.

## 3. Conflitos entre o prompt e o que está aprovado e em produção

1. **Unidade do crédito.** Hoje 1 crédito do cliente = 1 crédito da Lusha (fator 1): busca por resultado, e-mail 1, telefone 5, todos medidos. O prompt define **1 decisor válido = 1 crédito**, independentemente da fonte. Os limites dos planos (30/60/120/180) passariam a significar "decisores".
2. **Risco de margem.** Com a Lusha como complemento, um decisor com e-mail custa no mínimo (busca por resultado + 1) créditos e com telefone no mínimo (busca + 1 + 5) créditos da Lusha. Ao custo de planejamento de R$ 0,5294 por crédito (US$ 600 × R$ 6,00 ÷ 6.800), isso é de cerca de R$ 1,06 (só e-mail, supondo busca = 1) a R$ 3,71 (e-mail e telefone), contra R$ 1,35 de receita por crédito nos pacotes. **Cobrar 1 crédito por decisor sem distinguir telefone pode dar prejuízo por decisor.** A tarifa da busca é lida da conta da Lusha e não é publicada; os números acima são estimativas.
3. **Fontes gratuitas passariam a consumir a franquia.** QSA, site e LinkedIn hoje não cobram. O prompt manda cobrar. Isso reduz o que o plano Teste e os demais entregam de graça hoje.
4. **Base global de decisores.** Uma tabela de pessoas compartilhada entre clientes contraria o isolamento por tenant que acabou de ser fechado (A01). A forma segura é um identificador global **pseudonimizado** (hash de chave normalizada) usado só para deduplicar e para a chave de cobrança `tenant + empresa + id global`, sem guardar dado pessoal compartilhado.

## 4. Decisões do PO (2026-11-09) e o que foi entregue

Respostas: (1) **manter a cobrança atual da Lusha por consumo medido**; (2) QSA, site e LinkedIn **consomem a franquia**, conforme o prompt; (3) fornecedores: **Hunter e OpenEnrich**.

### 4.1 Entregue nesta etapa (tudo atrás de chave desligada por padrão)

- **Gerenciador** (`app/contexts/enriquecimento/gerenciador.py`): cascata *cadastro do cliente → fonte freemium → provedor pago* (o pago continua no caminho governado de `execucao.executar`, agora só com o que sobrou). Cota técnica por fonte e por mês (reserva atômica), cache por tenant + empresa + fonte (90 dias, configurável), disjuntor (3 falhas seguidas suspendem 30 min; chave recusada, 24 h; saldo do fornecedor acabado, até o mês seguinte), log por consulta sem dado pessoal. Falha de fonte gratuita nunca derruba a pesquisa paga.
- **Cobrança**: decisor que a empresa já tinha no cadastro = 0 crédito; decisor **novo** achado por fonte gratuita = **1 crédito** do cliente, tirado da reserva da empresa (idempotência `gratuito:{item}` no razão); o que o provedor pago devolver continua **debitado pelo consumo medido**. Só roda com `creditos_cliente_por_credito_provedor = 1`; com outro fator a etapa não executa e o fluxo é o de sempre.
- **Hunter** (`providers/contact_enrichment/hunter.py`): adaptador do Domain Search conforme a documentação oficial. Nasce **desligado** e com `permite_uso_comercial` em branco; só liga depois de o administrador registrar que os termos do fornecedor permitem uso comercial (a rota recusa ligar sem isso).
- **Verificação de e-mail pelo domínio** (`providers/email_validation/dominio.py`): sintaxe, domínio descartável e MX/A/AAAA. Nunca diz "confirmado".
- **Indicadores** (`GET /admin/enriquecimento/recursos`, só super_admin): `FREE_RESOURCE_UTILIZATION_RATE`, `PAID_PROVIDER_COST_AVOIDED` (estimativa que informa o método; `null` com o motivo quando não há histórico medido) e desempenho por fonte (taxa de sucesso, cache, latência, créditos do fornecedor). O nome do fornecedor pago não aparece em nenhum campo.
- Tabelas novas (aditivas): `enriquecimento_fonte` (plataforma) e `enriquecimento_consulta` (por tenant, com RLS). Nenhuma tabela existente foi alterada.

### 4.2 Não entregue, com o motivo

- **OpenEnrich não foi integrado.** É um verificador/localizador de e-mail em Node (CLI/MCP/interface local), licença AGPL-3.0, sem biblioteca para chamar de Python; a checagem de caixa por SMTP exige a porta 25 de saída, que o Render não libera. Entregue no lugar: o verificador por domínio acima. A porta 25 ainda precisa ser **testada no serviço publicado** antes de qualquer decisão sobre SMTP.
- **Hunter não foi chamado contra a API real** (não há chave): os testes provam a leitura do formato documentado, não que a integração funciona. Falta a chave, a confirmação de uso comercial e um teste real.
- **Cobrar QSA, site e importação do LinkedIn** (decisão 2) **não foi feito** fora da pesquisa governada: esses fluxos não têm reserva de crédito nem tela de confirmação, e a importação de planilha traz milhares de contatos de uma vez (7.947 no LinkedIn em produção). Cobrar sem reserva exige decidir o que acontece com saldo insuficiente. Dentro da pesquisa de decisores, o cadastro existente conta e não cobra de novo.
- **Identificador global pseudonimizado** (chave `tenant + empresa + decisor global`) e **proveniência por campo**: não implementados; hoje o decisor é identificado pelo nome normalizado dentro da empresa. Exigem migração própria e decisão de LGPD.
- **Prospeo, Snov.io e Apollo**: sem API gratuita utilizável (ver seção 2); nenhum gasto foi feito.

### 4.3 Ativação e reversão

1. Definir `HUNTER_API_KEY` no serviço (plano gratuito: 50 créditos/mês, 10 resultados por consulta).
2. Confirmar com o fornecedor que o uso em SaaS é permitido; registrar em `PUT /admin/enriquecimento/recursos/hunter` (`permite_uso_comercial: true`, `ativo: true`).
3. Definir `ENRIQUECIMENTO_GERENCIADOR_ATIVO=true`.
4. Reversão: voltar a chave para `false` (o fluxo volta a ser o de antes, sem migração), ou desligar só a fonte pela rota.

## 5. Riscos e pendências

1. **Margem na Lusha continua aberta**: mantida a cobrança medida, o risco do item 2 da seção 3 não muda. A fonte gratuita só reduz o gasto do provedor pago.
2. **A capacidade gratuita é pequena**: 50 créditos/mês do Hunter são menos de 1% dos 6.800 créditos mensais da Lusha. O ganho real vem sobretudo do cadastro que o cliente já tem.
3. **Janela de validade** do decisor (regra "dentro da validade = 0 crédito") hoje equivale a "já existe no cadastro"; não há vencimento por decisor.
4. **Telefone**: a fonte freemium não entrega telefone; pesquisa que pede telefone pula a etapa gratuita.

## Fontes

- Hunter: [preços](https://hunter.io/pricing), [termos](https://hunter.io/terms-of-service), [documentação da API](https://hunter.io/api-documentation), [central de ajuda: plano gratuito](https://help.hunter.io/en/articles/11060999-hunter-s-free-plan)
- Prospeo: [central de ajuda: planos](https://help.prospeo.io/en/article/plans-and-pricing-overview-cdloq9), [documentação da API](https://prospeo.io/api-docs)
- Snov.io: [preços](https://snov.io/pricing)
- Apollo: [preços](https://www.apollo.io/pricing), [preço da API](https://docs.apollo.io/docs/api-pricing)
