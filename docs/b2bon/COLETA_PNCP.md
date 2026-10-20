# Coleta agendada do PNCP — operação, monitoramento e recuperação

Sem IA em nenhum ponto. Reaproveita a ingestão idempotente de licitações (`licitacoes.ingerir`, única por tenant + fonte + id externo)
e o agendador que o projeto já usa (GitHub Actions → rota de cron), sem serviço novo e sem custo.

## O que o contrato real do PNCP exige (verificado em 2026-10-20, consulta de leitura)

`GET https://pncp.gov.br/api/consulta/v1/contratacoes/atualizacao` (usado desde a V5.2; `/publicacao` só vê edital novo) e `/publicacao`: `codigoModalidadeContratacao` é **obrigatório** (HTTP 400 sem ele — o
adapter anterior o tratava como opcional); `tamanhoPagina` aceita até 50 (100 devolve 400); a resposta traz `data`, `totalRegistros`,
`totalPaginas`, `numeroPagina`, `paginasRestantes`, `empty`; `uf` filtra no servidor; 204 = sem registros. Modalidades 1–19 em
`GET /api/pncp/v1/modalidades`. Um teste real de uma página (modalidade 6, UF SP, 1 dia) devolveu 50 itens normalizados corretamente.
O portal não publica limite de requisições na API de consulta que consultei: por isso a coleta é gentil (pausa de 0,5 s entre páginas,
janela curta, teto de 100 páginas (5.000 registros) por execução, retentativa com espera progressiva).

## Como funciona

- **Agendamento**: workflow `.github/workflows/cron-envios.yml`, job `coletar-licitacoes`, a cada 6 h (`43 */6 * * *`), chama
  `POST /api/v1/cron/coletar-licitacoes` com o segredo de cron. Também roda manualmente (`workflow_dispatch`). Sem scheduler pago.
- **Desligada por padrão em dois níveis**: (1) ambiente — `PNCP_HABILITADO=true` na API (sem isso a rota responde `desabilitada_no_ambiente`
  e não chama o PNCP); (2) tenant — `PUT /api/v1/bids/coleta/pncp/configuracao` (admin) com `ativa`, `modalidades` (1–19), `ufs`,
  `palavras_chave`, `janela_dias` (1–7) e `max_novas_por_execucao` (1–1000). Ativar exige ao menos uma modalidade e UF e/ou palavra-chave:
  coletar o país inteiro (milhares por dia) estouraria o banco.
- **Idempotência e retomada**: o cursor (`cursor_referencia`, AAAAMMDD) só avança quando a janela inteira termina. Falha ou teto atingido
  repete a janela; a ingestão só atualiza o que já existe (nunca duplica). Janela = cursor − 1 dia (publicação tardia/retificação) até no
  máximo 7 dias por execução, então um atraso longo é recuperado aos poucos. O progresso de cada página é gravado na hora.
- **Sem concorrência**: índice único parcial garante uma execução `em_andamento` por tenant e fonte. Execução esquecida há mais de 30 min é
  encerrada como `falhou` na próxima rodada.
- **Rodada compartilhada**: tenants com o mesmo filtro dividem as respostas do portal dentro da mesma rodada (menos chamadas).
- **Nunca apaga**: falha de atualização não remove nada já ingerido.

## O que fica registrado (`execucao_coleta_fonte`)

Disparo (agendado/manual), estado (`em_andamento`, `concluida`, `parcial`, `falhou`), início, conclusão, duração, consultados, inseridos,
atualizados, ignorados, páginas, tentativas HTTP, erro (texto controlado, sem credenciais), janela consultada e cursor. Consultas:
`GET /bids/coleta/pncp/execucoes`, `GET /bids/coleta/pncp/saude`, `POST /bids/coleta/pncp/executar` (admin, mesmas travas).

## Critérios de saúde e alertas

`GET /bids/coleta/pncp/saude` devolve: `desabilitada` · `nunca_executada` · `saudavel` · `atrasada` (nenhuma sincronização **concluída** há mais de
`COLETA_ATRASO_HORAS`, padrão 24 h; execução `parcial` não conta) · `falhando` (`COLETA_FALHAS_ALERTA` falhas seguidas, padrão 3). Além disso,
`última iniciada`, `última concluída`, `cursor`, `último erro` e a última execução completa.

Sinais operacionais: log de erro `COLETA_FONTE_FALHANDO` (e evento no Sentry quando há DSN) a partir da 3ª falha seguida; log de erro
`COLETA_FONTE_ATRASADA` por tenant atrasado a cada rodada; o job do GitHub fica vermelho (`curl --fail`) se a API recusar a chamada.

## Recuperação

1. Ver `GET /bids/coleta/pncp/saude` e o `ultimo_erro`. 2. PNCP fora do ar/429: nada a fazer, a próxima rodada (6 h) repete a janela;
a retentativa por chamada já espera 1 s, 2 s (respeita `Retry-After` até 30 s). 3. Erro 400: configuração de modalidade/UF — corrigir em
`PUT .../configuracao`. 4. Execução presa: encerrada sozinha após 30 min; ou chamar `POST .../executar`. 5. `parcial` recorrente: aumentar
`max_novas_por_execucao` ou estreitar o filtro (a execução para no teto de novas ou de 100 páginas). 6. Nada precisa ser limpo: reexecutar é seguro.

## Limitações conhecidas

- A coleta continua configurada **por tenant** (cada tenant define o próprio filtro), mas o fato público do edital vai para o **corpus comum** (`licitacao_publica`, uma linha por edital para toda a plataforma): ver `CORPUS_PUBLICO_LICITACOES.md`.
- Retificações: o registro é atualizado pelo id; não há histórico de versões do edital.
- Não coleta documentos/anexos do PNCP, só os metadados da contratação.
- **Ativação real pendente de validação externa**: o job agendado só existe depois do merge no `master`; é preciso `PNCP_HABILITADO=true`,
  `CRON_SECRET` no GitHub (já usado pelos outros jobs) e a configuração do tenant.

## Retificações, suspensões e cancelamentos (V5.2)

A coleta consulta `/contratacoes/atualizacao` (data da última atualização), então edital retificado, suspenso, revogado ou anulado volta à janela.
Cada licitação guarda `situacao_externa` e `atualizado_externo_em`. Mudança de situação ou de conteúdo conta em `alterados_na_fonte` da execução
(auditoria `licitacao_alterada_na_fonte`). Situação que começa com revogad/anulad/suspens/cancelad faz a tela de Licitações mostrar o selo
"{situação} na fonte" (`externa_exige_atencao`); **o sistema não muda sozinho o status interno** nem apaga: quem decide é o usuário. Migração
`c9f1b3d5e7a9` (2 colunas em `licitacao`, 1 em `execucao_coleta_fonte`; downgrade remove as colunas e perde só esses metadados).

## Retenção dos históricos

Poda diária (`POST /cron/podar-historicos`, passo no `cron-envios.yml`): cache de IA vencido; execuções de coleta com mais de
`RETENCAO_EXECUCAO_COLETA_DIAS` (90) preservando sempre a última `concluida` por tenant e fonte (guarda o cursor) e as `em_andamento`; coletas de
site com mais de `RETENCAO_COLETA_SITE_DIAS` (180) com seus indicadores, preservando a mais recente e a última bem-sucedida de cada conta, as
confirmadas manualmente e as em andamento. Idempotente; reprocesso que sobrevive perde só a ligação com a coleta original apagada.
