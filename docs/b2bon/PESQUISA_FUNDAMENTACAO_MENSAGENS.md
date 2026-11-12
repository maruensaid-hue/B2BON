# Pesquisa: fundamentação verificável das mensagens de prospecção — dados de partida e desenho técnico

Documento de apoio à proposta de pesquisa (FAPESP/PIPE). **É um desenho: nada aqui foi implementado nem migrado.** A única peça de código já entregue é a exportação anonimizada do corpus (`scripts/ops/exportar_corpus_anonimizado.py`, somente leitura).

## 1. Ponto de partida medido em produção (tenant `cyberfort`, 10/11/2026, só totais)

| Item | Valor |
|---|---|
| Mensagens hoje na tabela | 558 (e-mail 334, LinkedIn 135, WhatsApp 89) |
| Mensagens já propostas pela IA segundo a trilha | 895 — **337 não existem mais na tabela** (foram apagadas) e não entram em nenhum corpus |
| Situação das mensagens | enviadas 90 (84 e-mail + 6 LinkedIn, para 44 contatos distintos), aprovadas e não enviadas 133, canceladas 334, aguardando aprovação 1 |
| Decisões na tabela de aprovação | 338 aprovadas, 220 rejeitadas |
| Rejeições humanas registradas na trilha | no máximo 13 — as demais "rejeitadas" são cancelamentos administrativos em massa, sem decisão sobre o conteúdo |
| Edições humanas registradas | 1 |
| **Respostas** | **0**: nenhum e-mail recebido, nenhuma conversa de qualificação, nenhum evento de resposta detectada |
| Contas | 15.424 |
| Contas com páginas do site guardadas | 662 |
| Contas com sinal vigente (evidência estruturada) | 108 (933 sinais) |
| Contas com mensagem | 60 — **só 1** tem sinal vigente |

**Consequências para a pesquisa**
1. A decisão humana dá pouco rótulo: com 1 edição e no máximo 13 rejeições reais, o vendedor praticamente aprova em lote. O desfecho principal tem de vir de **anotação** das afirmações, não do comportamento do vendedor.
2. Não existe dado de resposta. Taxa de resposta só pode ser medida a partir de agora, e é um desfecho exploratório.
3. As mensagens existentes quase não têm evidência estruturada por trás (1 de 60 contas). Elas servem como linha de base de afirmações sem lastro, mas não para treinar ou calibrar um verificador de "sustentada".
4. Nem tudo o que a IA gerou foi preservado: 337 mensagens foram apagadas. A pesquisa precisa de uma regra de não apagar o que alimenta o corpus.

## 2. O que conta como evidência válida

Uma afirmação é **sustentada** se existir um registro guardado que a implique, com origem, trecho ou campo, data de coleta e confiança.

| Fonte | Vale como evidência de | Observações |
|---|---|---|
| Sinal de conta (`sinal_conta`) | fatos observados no site e no cadastro (tem página de carreiras, usa pixel etc.) | já guarda fonte, URL, trecho, confiança (0–1), data e histórico; só entram os marcados para a mensagem e com confiança ≥ 0,6 |
| Cadastro público de CNPJ | razão social, CNAE, porte, UF, abertura, situação, sócios | dado público; guardar a data da base |
| Texto de página do site | o que a página diz | hoje é **sobrescrito** a cada coleta; precisa de instantâneo (seção 3) |
| Histórico da conta | interações já registradas | atividades, reuniões, mensagens anteriores |
| Dado informado pelo usuário (ex.: importação do LinkedIn) | cargo e relação declarados | fonte própria, confiança menor, sempre rotulada |
| **Não vale** | — | hipóteses do perfil de cliente (ICP), resumo do site gerado por IA (é derivado, serve de pista) e o próprio texto gerado |

Janela de validade por fonte (por exemplo, site mais velho que N dias deixa de sustentar afirmações no tempo presente): `[definir no protocolo]`.

## 3. Desenho de dados (aditivo, sem alterar tabela existente)

Princípios: tabelas novas, migração só de criação, isolamento por empresa (RLS tenant direto, como as demais), registros de evidência **imutáveis** (append-only), nenhuma mudança no que a plataforma faz hoje.

### 3.1 `evidencia_conta` — instantâneo imutável do que se sabia
Resolve o problema de o texto do site ser sobrescrito.

| Coluna | Descrição |
|---|---|
| `id`, `tenant_id`, `conta_id` | — |
| `tipo` | `sinal` · `pagina_site` · `cadastro_cnpj` · `historico` · `informado_usuario` |
| `fonte`, `url`, `trecho` | origem e o trecho exato que entrou na geração |
| `hash_conteudo` | SHA-256 do trecho; evita duplicar o mesmo texto |
| `coletado_em` | quando a informação foi obtida (não quando foi gravada) |
| `confianca` | 0–1, quando existe |
| `origem_ref` | id do `sinal_conta`/`conteudo_pagina_site` de onde veio |
| `criado_em` | — |

Única por (`conta_id`, `tipo`, `hash_conteudo`). Gravada **no momento da geração**, com os trechos que entraram no prompt.

### 3.2 `mensagem_geracao` — o que produziu cada mensagem (1:1 com `mensagem`)
`mensagem_id` (único), `versao_pipeline` (ex.: `atual`, `fundamentado_v1`), `braco` (`controle`/`teste`/`nao_experimental`), `experimento_id`, `modelo`, `correlation_id` (liga ao `registro_uso_ia`, que já guarda modelo, tokens e custo; a mensagem ainda não existe na hora da chamada, por isso o vínculo é por `correlation_id`), `prompt_hash`, `criado_em`.

### 3.3 `mensagem_evidencia` — quais evidências alimentaram a mensagem
`mensagem_id`, `evidencia_id`, `entrou_no_prompt` (bool). N:N.

### 3.4 `mensagem_afirmacao` — o resultado da verificação
| Coluna | Descrição |
|---|---|
| `mensagem_id`, `ordem` | posição da afirmação no texto |
| `inicio`, `fim` | trecho da mensagem (índices de caractere) |
| `tipo` | `fato_sobre_empresa` · `fato_sobre_pessoa` · `hipotese` · `oferta_propria` · `chamada_para_acao` · `outro` |
| `veredito` | `sustentada` · `sem_lastro` · `hipotese_como_fato` · `nao_verificavel` · `pendente` |
| `evidencia_id` | evidência que sustenta (nulo quando não há) |
| `justificativa` | frase curta |
| `metodo` | `anotador_humano` ou `verificador_automatico:<versão>` |
| `anotador_ref` | pseudônimo do anotador (para medir concordância) |
| `criado_em` | — |

Única por (`mensagem_id`, `ordem`, `metodo`, `anotador_ref`): a mesma afirmação pode ter vários vereditos (dois anotadores, mais o verificador), que é o que permite medir concordância e a precisão do verificador.

### 3.5 `experimento_alocacao` — grupos de controle e teste
`experimento_id`, `decisor_id`, `braco`, `semente`, `sorteado_em`. O sorteio é **por contato** (não por mensagem), estratificado por canal e segmento, com a semente registrada para ser reprodutível. O A/B atual (`variante_ab`) compara enquadramentos de texto e fica como está.

## 4. Fluxo

1. **Geração:** a plataforma monta o prompt como hoje e grava o instantâneo das evidências que entraram (3.1, 3.3) e a linha de 3.2.
2. **Extração e verificação:** um verificador separa o texto em afirmações (3.4) e procura, para cada fato, uma evidência entre as da conta.
3. **Braço controle:** o verificador roda em **modo sombra** — registra os vereditos, mas não altera nada. É a linha de base.
4. **Braço teste:** o verificador age — afirmação `sem_lastro` ou `hipotese_como_fato` é reescrita ou removida; se não for possível, a mensagem é marcada para o vendedor.
5. **Aprovação humana** (obrigatória, como hoje). A **medição acontece antes** dela e a rejeição de fato inventado vale em qualquer braço; assim nenhum fato inventado precisa sair para ser medido.
6. **Desfechos:** edição e rejeição pelo vendedor (já registradas) e resposta (a partir de agora, depois de corrigida a captura).

## 5. Métricas

- **Principal:** afirmações sem lastro por mensagem (e proporção de mensagens com pelo menos uma), pela anotação humana em amostra cega, com concordância entre anotadores.
- **Qualidade do verificador:** precisão e cobertura contra a anotação humana.
- **Custo da correção (H2):** taxa de aprovação sem edição, rejeição, tamanho e personalização do texto.
- **Exploratória:** taxa de resposta — com e-mail frio é um evento raro e o volume atual é pequeno; não sustenta conclusão sozinha.
- Tamanho de amostra, nível de significância e metas: `[definir no protocolo, antes de rodar]`.

## 6. Riscos e decisões que ficam abertas

- **Custo e latência da verificação:** o verificador faz chamadas extras de IA por mensagem. Medir no protocolo e decidir entre verificação por regra (barata, cobre menos) e por modelo.
- **Falso positivo do verificador:** pode apagar texto bom e deixar a mensagem genérica; é exatamente o que H2 mede.
- **Dados pessoais:** os trechos de evidência e das afirmações podem conter dado de terceiros. Ficam no tenant (RLS), com a mesma retenção da conta; o que sai da empresa passa pelo corpus anonimizado. `[confirmar base legal e tratamento para pesquisa com o jurídico]`
- **Não apagar o que alimenta a pesquisa:** hoje a limpeza de rascunhos apaga mensagens (337 já se perderam). É preciso uma regra de cancelar sem apagar para tudo o que entra no corpus.
- **Captura de respostas:** zero respostas registradas pode ser ausência de resposta ou falha de captura. Verificar antes de usar resposta como desfecho.
- **Segundo cliente:** o desenho é por tenant, então um piloto com outro cliente exige apenas habilitar o mesmo fluxo nele. `[a confirmar interesse]`

## 7. Fases sugeridas

| Fase | Entrega |
|---|---|
| 0 (feita) | exportação anonimizada do corpus, com revisão manual; contagens de produção |
| 1 | tabelas 3.1–3.4, instantâneo de evidência na geração (só registra, sem mudar comportamento) e regra de não apagar |
| 2 | anotação humana de uma amostra e protocolo estatístico fechado |
| 3 | verificador em modo sombra nos dois braços; medir precisão contra a anotação |
| 4 | braço de teste atuando; avaliação offline e online controlada |
| 5 | relatório, corpus anonimizado e publicação |
