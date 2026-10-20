# Corpus público comum de licitações (V5.2.1, Fase 3)

Um edital é um **fato público**: existe uma única linha por `(fonte, id externo)` em toda a plataforma. Cada tenant que o acompanha guarda a sua **cópia privada** (score, anotações, estratégia, conta, oferta, responsável, resultado), ligada ao fato por `licitacao.corpus_id`. Antes, cada tenant gravava o próprio texto do mesmo edital.

## O que é público e o que é privado

| Público — `licitacao_publica` (sem `tenant_id`) | Privado — `licitacao` (por tenant) |
|---|---|
| fonte, id externo, órgão (nome, CNPJ), UF, município | `tenant_id`, `status` interno do funil |
| título, objeto, modalidade (e código da fonte) | `conta_id`, `oferta_id`, `responsavel_usuario_id` |
| datas (publicação, proposta), valor estimado | concorrentes, parceiros, vencedor, valor da proposta, motivo do resultado |
| situação na fonte, quando a fonte atualizou, URL oficial | prazo de esclarecimento, análises, requisitos, documentos, decisões Go/No-Go |
| versão, hash do conteúdo, histórico de retificações | ICPs, scores, preferências de alerta (Fase 4) |

Garantias verificadas por teste: (1) um teste de esquema impede que `licitacao_publica` ganhe coluna de tenant ou de dado privado; (2) o dado privado editado por um tenant não aparece no corpus nem para o outro tenant; (3) `ja_acompanho` revela só o vínculo do próprio tenant — **não há contador de quem mais acompanha**; (4) apagar a cópia privada de um tenant não altera o fato nem a cópia dos outros.

## Fluxo

1. **Coleta** (`bids.coleta`, sem IA, agendada): cada página do PNCP é filtrada pelo critério do tenant; os itens relevantes passam por `licitacoes.ingerir_detalhado`, que (a) grava o fato no corpus via `corpus.registrar` e (b) cria/atualiza a cópia privada apontando para ele. Tenants com o mesmo filtro dividem a resposta da fonte (já existia) e, agora, também a linha do corpus.
2. **Só o relevante entra no corpus** (a união dos filtros dos tenants). Não se baixa o país inteiro: o custo de armazenamento é **menor ou igual** ao de antes, nunca maior.
3. **Consulta**: `GET /bids/corpus` (filtros: `q`, `uf`, `modalidade`, `situacao`, `desde`; paginação por cursor), `GET /bids/corpus/{id}` (com histórico), `POST /bids/corpus/{id}/acompanhar` (cria a cópia privada; 201 ao criar, 200 se já acompanhava).

## Deduplicação, retificação e ordem

- **Idempotência**: a chave `(fonte, id externo)` é única no banco. Recoletar sem mudança não cria linha, não gera evento e só atualiza `ultima_coleta_em`.
- **Retificação**: hash SHA-256 do conteúdo público (título, objeto, órgão, CNPJ, modalidade, datas, valor, situação, URL). Mudou → `versao + 1` e evento `retificada` com `{campo: [antes, depois]}`. Mudança de situação (Divulgada → Suspensa/Anulada/Revogada) gera evento próprio `situacao_alterada`. Fonte que não informa situação **não apaga** a que já se sabe.
- **Localização** (UF, município, código da modalidade) é enriquecimento: preenche em silêncio e não conta como retificação.
- **Ordem**: leitura mais antiga que o estado guardado (`atualizado_externo_em` menor) não desfaz uma atualização mais nova.
- **Corrida**: duas coletas inserindo o mesmo edital terminam com uma linha (savepoint; na violação de unicidade a segunda atualiza a existente).
- **Recuperação**: nada é confirmado antes do commit do chamador; falha no meio do lote desfaz a transação inteira e a reexecução converge para o mesmo estado, sem duplicar (teste dedicado).

## Migração `d1b3e5a7c9f1` e compatibilidade

Cria `licitacao_publica` e `evento_licitacao_publica`, adiciona `licitacao.corpus_id` (FK, índice) e **faz o backfill**: uma linha pública por `(fonte, id externo)` já ingerido (a partir da cópia mais recente) e vincula **todas** as cópias privadas. Licitação manual não entra. O algoritmo de hash fica congelado dentro da migração e um teste garante que é idêntico ao do código (senão a primeira recoleta geraria falsa retificação). Validada sobre dados anteriores em SQLite; o PostgreSQL roda no job de migrações do CI. **Downgrade** remove o vínculo e as duas tabelas: perde o histórico de retificações e UF/município do corpus; as licitações privadas ficam intactas.

As estruturas existentes foram **estendidas, não substituídas**: `Licitacao`, `ExecucaoColetaFonte`, o coletor e `ingerir_detalhado` continuam sendo o único caminho de ingestão; o espelho para o módulo de sourcing não foi alterado.

## Retenção

Poda diária: edital sem **nenhuma** cópia privada e não coletado há mais de 365 dias (`RETENCAO_CORPUS_SEM_VINCULO_DIAS`) sai com o seu histórico. Edital que algum tenant acompanha nunca sai.

## Limites e riscos

- **Termos de uso**: só o PNCP está integrado; é portal de dados públicos (Lei 14.133). Antes de ligar **outra** fonte ao corpus, verificar os termos dela (restrição legal/contratual de redistribuição) — o modelo é por `fonte`, então uma fonte restrita pode ficar fora do corpus compartilhado sem mudar o esquema.
- O corpus só contém o que algum tenant pediu para coletar. Um tenant sem filtro não "enxerga o Brasil"; isso é deliberado (custo de armazenamento).
- Sem texto integral nem anexos do edital: só metadados da contratação.
- A coleta continua **desligada em produção** (`PNCP_HABILITADO`); nada disso foi ativado.
