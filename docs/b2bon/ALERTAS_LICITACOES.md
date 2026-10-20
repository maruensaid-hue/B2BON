# Alertas de oportunidades de licitação por regra/ICP (V5.2.1, Fase 4)

Sem IA. Correspondência **determinística e explicável** sobre o corpus público (`CORPUS_PUBLICO_LICITACOES.md`). O alerta é **compatibilidade com as regras do tenant**, nunca certeza de elegibilidade ou de vitória, e a tela e o e-mail dizem isso.

## Como funciona

1. A coleta grava o fato público no corpus; cada mudança (novo edital, retificação, mudança de situação) vira um evento (`evento_licitacao_publica`).
2. `POST /cron/processar-alertas-licitacoes` (passo do job `coletar-licitacoes`, depois da coleta) percorre os tenants com regra ativa. Para cada um, `avaliar_tenant` lê os eventos novos desde o **cursor do tenant**, avalia o **estado atual** do edital contra as regras e grava **um alerta por (tenant, edital)**.
3. `entregar` envia **um resumo** por e-mail de sistema aos administradores do tenant — **desligado por padrão** (`ALERTAS_LICITACAO_EMAIL_HABILITADO=false`). Com ele desligado os alertas aparecem no painel e nada sai.
4. O usuário vê, filtra e age em `/bids/alertas` (link na tela de Licitações): marcar visto, dispensar, **acompanhar** (cria a cópia privada da licitação a partir do corpus; idempotente) e abrir a **fonte oficial**.

## Regra de alerta (privada do tenant)

Campos: nome, ativa, **ICP opcional** (sem UFs próprias, a regra herda as UFs do ICP), palavras-chave, palavras a excluir, UFs, modalidades, faixa de valor, dias mínimos de prazo, "usar portfólio" (soma as palavras do nome da oferta ativa), compatibilidade mínima (0–100) e frequência (`imediata` = a cada coleta; `diaria` = no máximo um resumo a cada ~20 h). Só administradores criam/alteram/excluem. O `icp_id` é validado contra o tenant (um ICP de outro tenant é recusado com 404). Criar ou alterar uma regra volta o cursor a zero: ela passa a enxergar o corpus que já existia (a unicidade impede alerta duplicado).

**Palavra-chave (ou portfólio) é obrigatória** — sem ela a regra casaria com todo edital da UF e viraria ruído.

## Pontuação (explicável)

`compatibilidade = pontos obtidos ÷ pontos possíveis dos critérios que a regra definiu`. Pesos: palavras 60 (1 palavra = 40, 2 = 50, 3 ou mais = 60), UF 20, valor 10, modalidade 5, prazo 5. Critério **violado exclui** (palavra excluída, UF fora, valor fora da faixa, modalidade diferente, prazo menor que o mínimo). Dado que a fonte **não informa** (UF, valor, prazo) não exclui, mas **não pontua** e o fator diz "a fonte não informou" — a incerteza baixa a compatibilidade em vez de ser tratada como acerto. Prazo de proposta vencido nunca gera alerta; edital que já nasce suspenso/anulado/revogado/cancelado também não. Cada alerta guarda `fatores` (`{fator, pontos, maximo, detalhe}`) e as regras que casaram; com várias regras no mesmo edital fica **um** alerta com a melhor pontuação.

Busca de palavra: sem acento e sem diferenciar maiúscula; a palavra começa em fronteira de palavra (aceita plural/derivação, `licença` casa `licenças`; `TI` não casa dentro de `gestão`).

## Retificação, suspensão e cancelamento

Quando o corpus muda de versão para um edital já alertado, o alerta atualiza a situação, vira `motivo=atualizada` e `atualizacao_nao_vista=true` (a tela mostra "Atualizado na fonte" e a situação), **exceto se o usuário o dispensou** (continua dispensado; o snapshot acompanha em silêncio). O e-mail volta a ser enviado só quando a situação passa a exigir atenção (suspensa/anulada/revogada/cancelada) ou quando prazo/valor foram retificados; outras mudanças atualizam sem notificar.

## Entrega: registro, erro e reprocessamento

Cada alerta guarda `entrega_estado` (`pendente`, `enviada`, `falhou`, `desistida`, `desligada`, `sem_destinatario`), tentativas, último erro (texto controlado, sem credenciais) e `entregue_em`. Falha → `falhou` e é **reprocessada no ciclo seguinte**; após 3 tentativas → `desistida`. O resumo traz até 10 oportunidades e "… e mais N no painel" (**um** e-mail por administrador, não um por edital). Sai pelo provedor de **sistema** (`get_email_provider`), sem `mensagem_id` nem pixel: não conta no outreach nem na reputação de e-mail de cadência.

## Recuperação e idempotência

Cursor por tenant em `estado_alertas_licitacao`; unicidade `(tenant, edital)` no banco; falha no meio da avaliação desfaz o lote e a reexecução converge para o mesmo estado (teste dedicado). Reexecutar o cron não cria alerta nem e-mail novos.

## Ativação do PNCP — **nada foi ativado**

O PNCP continua desligado em produção (`PNCP_HABILITADO` ausente) e o e-mail dos alertas também. Para ligar, o responsável pelo produto precisa decidir e informar: (1) as **UFs** e **palavras-chave** da coleta de cada tenant (a coleta recusa ativar sem ao menos UF ou palavra-chave); (2) as regras de alerta; (3) `PNCP_HABILITADO=true` e `ALERTAS_LICITACAO_EMAIL_HABILITADO=true` na API; (4) o merge no `master` (o workflow agendado só existe lá). Nenhuma UF ou palavra-chave foi inventada nesta fase.

## Retenção

Alertas com mais de 180 dias cujo estado não é `acompanhado` saem na poda diária; o corpus que um alerta referencia não é podado.

## Limites

- Correspondência por texto do objeto: não lê o edital completo nem os anexos; CNAE do órgão não entra (não descreve o objeto contratado).
- O alerta usa só os editais que a coleta já gravou no corpus (a união dos filtros de coleta dos tenants). Não "enxerga o Brasil inteiro".
- Compatibilidade não substitui a análise de habilitação (Go/No-Go e matriz de conformidade, que já existem e continuam sendo do usuário).
