# Manual do Usuário — B2B ON

Guia funcional da plataforma B2B ON: o que cada módulo faz, como usar
no dia a dia e como funcionam os planos de licença. Para instalar/rodar
o projeto ou fazer deploy, veja [README.md](README.md) e
[DEPLOY.md](DEPLOY.md) — este documento é sobre o **uso** da plataforma
já em funcionamento.

## Sumário

1. [Conceitos gerais](#1-conceitos-gerais)
2. [CRM](#2-crm)
3. [Rede Social](#3-rede-social)
4. [MAP — Motor de Alta Performance](#4-map--motor-de-alta-performance)
5. [PREDATOR](#5-predator)
6. [Administração](#6-administração)
7. [Modelos de licença](#7-modelos-de-licença)

---

## 1. Conceitos gerais

### Tenant

Cada empresa que usa a B2B ON é um **tenant** — um espaço isolado de
dados (contas, negócios, mensagens, etc.). Um usuário sempre pertence a
exatamente um tenant e só enxerga os dados dele. A exceção deliberada é
a **Rede Social**, onde tenants diferentes interagem entre si (perfis,
conexões, mensagens) de forma controlada.

### Papéis de usuário

Cada usuário tem um papel (`papel`), que define o que ele pode fazer:

- **`user`** — uso normal do dia a dia: CRM, Prospecção, Cadências,
  Aprovações, Reuniões, Rede Social — e o **MAP**, mas só das contas em
  que é o vendedor responsável (sua própria carteira).
- **`admin`** — tudo que `user` faz, mais gerar/revogar convites de
  cadastro para novos usuários do próprio tenant. No MAP, é o gestor:
  vê a carteira de todos os vendedores do tenant, com filtro por
  vendedor, e é quem atribui qual vendedor é responsável por cada conta.
- **`super_admin`** — reservado à equipe da própria B2B ON (CyberFort):
  além de tudo acima, enxerga a área de **Administração** (Tenants,
  Licenças, Planos). O MAP dele é outro: monitora a saúde de *todos os
  tenants assinantes* da B2B ON, não as contas de um tenant específico
  — ver seção 4 para a diferença entre os dois MAPs.

### Entrando na plataforma

Existem dois jeitos de uma conta de usuário nascer:

- **Convite normal** (`admin`/`super_admin` gera em Rede Social ou via
  API `/convites`): cria um usuário dentro de um tenant que **já é
  cliente pagante** — acesso completo aos módulos que a licença cobre.
- **Convite-vitrine** (qualquer usuário gera na tela **Rede Social**):
  cria um **tenant novo e independente**, sem licença nenhuma — a
  empresa convidada entra só para participar da Rede Social, sem virar
  cliente. Veja a seção [7](#7-modelos-de-licença) para o que isso
  restringe na prática.

### O que cada tela mostra depende da licença

Quem não tem licença ativa só vê a **Rede Social** no menu — é o único
módulo liberado por padrão. Todo o resto (CRM, Prospecção, Cadências,
Aprovações, Reuniões, MAP, Configuração) exige licença ativa; a API
recusa o acesso com uma mensagem clara se isso não for atendido.

---

## 2. CRM

Funil de vendas do próprio tenant — negociações com as contas que a
Prospecção (PREDATOR) gerou ou que entraram por outro canal.

- **Pipeline (Kanban)**: colunas = estágios do funil (ex.: Qualificação,
  Proposta, Negociação, Ganho, Perdido), cada uma com o total de
  negócios e valor. Arrastar/mover um negócio para outra coluna
  atualiza o estágio; um negócio pode ser criado direto informando a
  conta, nome do negócio e valor.
- **Dashboard**: dois blocos alimentados pelo CRM —
  - **Funil de vendas**: quantidade de negócios por estágio (gráfico de
    barras) e taxa de conversão do período.
  - **Economia**: LTV médio, CAC, taxa de churn, novos clientes e
    cancelamentos no mês.
- **Ligação automática com o PREDATOR**: quando uma reunião de
  prospecção é confirmada, o CRM ganha automaticamente uma oportunidade
  vinculada à conta — não é preciso lançar isso manualmente.

---

## 3. Rede Social

Rede de relacionamento **entre tenants** da B2B ON — parceiros,
fornecedores, clientes de módulos diferentes se conectando e trocando
mensagens. É o único módulo acessível sem licença ativa.

- **Meu perfil**: nome de exibição, setor, site e descrição — como sua
  empresa aparece para as outras.
- **Diretório de empresas**: lista as demais empresas da rede, com a
  oferta principal de cada uma (se cadastrada em Configuração) e o
  status da conexão (nenhuma / pendente enviada / pendente recebida /
  aceita).
- **Conectar**: enviar um pedido de conexão a outra empresa; ela recebe
  em "Conexões pendentes" e pode aceitar ou recusar. Só depois de
  aceita é possível trocar mensagens.
- **Mensagens**: conversa 1:1 entre duas empresas conectadas.
- **Convidar empresa** (convite-vitrine): qualquer usuário do tenant
  pode gerar um link de convite (com validade em horas) para uma
  empresa de fora entrar na Rede Social. Copie o link e envie por fora
  da plataforma (e-mail, WhatsApp); ao abrir, a pessoa preenche razão
  social, CNPJ (opcional), nome, e-mail e senha, e um tenant novo é
  criado na hora — sem precisar de nenhuma aprovação manual do seu
  lado. O convite pode ser revogado enquanto estiver "disponível"
  (ainda não usado).
- **Indicações**: quando uma empresa indicada por dentro da rede vira
  cliente, isso é registrado automaticamente — não há tela dedicada, é
  refletido nos indicadores administrativos.

---

## 4. MAP — Motor de Alta Performance

O MAP é para todo mundo — é um dos diferenciais centrais da plataforma,
não uma ferramenta interna da CyberFort. O que muda por papel é **o que**
cada um enxerga, não se tem acesso:

| Papel | O que o MAP mostra |
|---|---|
| `user` (vendedor) | Só as contas em que ele é o vendedor responsável — a própria carteira. |
| `admin` (gestor) | Todas as contas do tenant, de todos os vendedores, com filtro por vendedor. |
| `super_admin` (B2B ON) | Os tenants **assinantes da B2B ON** (visão cross-tenant, inalterada — é o negócio da própria CyberFort, não as contas de um tenant). |

Nas duas primeiras linhas o MAP mede a saúde das **contas** (clientes e
prospects dentro do CRM/PREDATOR do tenant); na linha do `super_admin`
o MAP mede a saúde dos **tenants** (empresas que assinam a B2B ON). São
dois rankings com a mesma metodologia de score, aplicados a coisas
diferentes — o `super_admin` não vê as contas internas de cada tenant
no MAP, só a saúde do tenant como cliente da B2B ON.

### 4.1 MAP de contas (user/admin)

- **Visão geral**: score médio, quantidade de contas em situação
  crítica/atenção/saudável e valor de pipeline aberto em risco.
- **Filtro por vendedor** (só para `admin`): reduz o ranking e os KPIs
  a um vendedor específico — útil para o 1:1 de gestão.
- **Ranking de saúde**: contas ordenadas por score; o gestor vê também
  a coluna de qual vendedor é o responsável.
- **Detalhe da conta**: score de risco (0–100) com os sinais que o
  compõem, histórico de interações, **Registrar interação** (contato,
  ticket de suporte, reclamação, feedback positivo, reunião remarcada,
  menção a concorrente — mesmo vocabulário do MAP de tenants) e
  **Gerar script de resgate** (roteiro de reengajamento gerado por IA).
- **Atribuir vendedor a uma conta**: no detalhe da conta em
  **Prospecção** (`ContaDetalheModal`), o campo "Vendedor responsável
  (MAP)" — editável só por `admin`/`super_admin` — define de quem é
  aquela conta. Sem essa atribuição, a conta não aparece para nenhum
  `user`, só para o gestor.

### 4.2 MAP de tenants (super_admin)

- **Visão geral**: score médio de saúde, quantidade de tenants em
  situação crítica/atenção/saudável e valor mensal total em risco.
- **Ranking de saúde**: todos os tenants ordenados, com badge de
  classificação (crítico / atenção / saudável) e valor em risco de
  cada um.
- **Detalhe do tenant**: ao clicar em um tenant no ranking —
  - Score de risco (0–100) e os sinais que compõem esse score (dias
    sem contato, tickets, reclamações, etc., cada um com seu peso).
  - Histórico de interações registradas.
  - **Registrar interação**: toda vez que a equipe de sucesso do
    cliente falar com o tenant, vale registrar aqui — é o que alimenta
    o score.
  - **Gerar script de resgate**: para tenants em risco, a IA gera um
    roteiro de conversa personalizado (com a justificativa dos pontos
    levantados) para reverter o risco de cancelamento.

---

## 5. PREDATOR

O motor de prospecção assistida por IA. Cobre da geração da lista de
contas até a reunião qualificada, sempre com aprovação humana antes de
qualquer envio.

### 5.1 Configuração (pré-requisito)

Antes de gerar cadências, cadastre em **Configuração**:

- **Oferta**: nome, descrição, diferenciais e provas sociais do que
  está sendo vendido. **A descrição, os diferenciais e as provas
  sociais entram literalmente no texto que a IA usa para escrever cada
  mensagem** de e-mail/WhatsApp da cadência — não são um resumo interno,
  são a matéria-prima do discurso de vendas. Junto com as dores/gatilhos
  do ICP ativo, é o que dá contexto de negócio à mensagem gerada (sem
  isso, a IA só saberia o nome da oferta). Só uma oferta fica ativa por
  vez; cadastrar uma nova substitui a anterior como ativa.
- **Tom e restrições de comunicação**: o tom da comunicação (ex.:
  "consultivo") e uma lista do que a IA nunca deve mencionar (ex.:
  preço, concorrentes, desconto).

### 5.2 Prospecção — ICPs e contas

- **ICP (Perfil de Cliente Ideal)**: segmento, porte (micro / pequeno /
  demais), região, CNAEs, UFs, dores e gatilhos que definem quem
  prospectar. Um ICP tem versões — "Nova versão" cria uma versão nova
  do mesmo ICP; "Clonar" cria um ICP independente a partir dele.
- **Gerar lista**: a partir de um ICP ativo, gera N contas reais a
  partir da base da Receita Federal que batem com os critérios — cada
  execução **consome franquia mensal** (ver seção 7).
- **Importar de evento**: cole a lista de participantes de um evento
  (direto do Excel/Planilhas ou CSV) — reconhece cabeçalho em qualquer
  ordem (Nome, Empresa, Cargo, E-mail, Telefone). Empresas repetidas
  viram uma única conta; participantes duplicados são ignorados. Essa
  via **não consome franquia** — só a geração via ICP consome.
- **Contas**: tabela com nome, CNPJ, score de aderência ao ICP e status
  (`prospectada` → `priorizada` ou `descartada`). "Ver detalhes" abre
  decisores mapeados, enriquecimento de dados via BrasilAPI (dados
  cadastrais oficiais do CNPJ), e ações de priorizar/descartar.
- **Pesquisar empresa (site)**: dentro do detalhe da conta (exige a
  conta ter um domínio cadastrado). Varre a home e páginas internas do
  próprio site (sobre, investidores, notícias, privacidade) — não sai
  para a web aberta — e pede à IA um resumo de porte, sinais de
  crescimento, marcos/linha do tempo, novos projetos/produtos e se há
  política de privacidade ou menção a LGPD/DPO publicada, fechando com
  uma hipótese de dor. Cada página efetivamente pesquisada fica
  registrada como um campo `pagina_pesquisada`, funcionando como um
  pequeno histórico da pesquisa feita — não é só um diagnóstico de
  LGPD, serve de insumo para qualquer oferta cadastrada.
- **Franquia**: os três indicadores no topo da tela (limite do plano,
  usado no mês, restante) mostram o consumo em tempo real.

### 5.3 Cadências

Sequência de toques multicanal (e-mail, WhatsApp, LinkedIn) gerada por
IA para abordar as contas.

1. **Criar cadência**: nome, tipo (prospecção ou nutrição) e a
   sequência de toques (mínimo 5, em pelo menos 2 canais), cada um com
   canal e intervalo de dias em relação ao toque anterior. Nasce como
   `rascunho`.
2. **Gerar mensagens para um lote**: com a cadência em rascunho,
   escolha um ICP e marque as contas — a IA gera o texto de cada
   mensagem de cada toque, respeitando oferta/tom/restrições. Contas
   sem decisor mapeado ficam de fora (é preciso mapear um decisor
   antes). As mensagens geradas vão para a **fila de Aprovação**, e a
   cadência muda para `aguardando_aprovacao`.
3. **Ativar cadência**: depois que a fila de aprovação está revisada,
   ativar a cadência (`ativa`) faz os envios entrarem na fila de envio
   real, respeitando o agendamento de cada toque. É neste momento que a
   franquia é consumida para as contas novas do lote (ver seção 7).

### 5.4 Fila de Aprovação

Toda mensagem que a IA gera passa por aqui antes de sair — é o "mediante
aprovação" do PREDATOR.

- Lista mensagens pendentes, com filtro por canal.
- **Editar**: o texto é editável antes de aprovar.
- **Aprovar** / **Rejeitar**: individual, ou "Aprovar todas" para o
  lote inteiro visível no filtro atual.
- Só mensagens aprovadas entram na fila de envio.

### 5.5 Disparo e rampa de aquecimento

Mensagens aprovadas ficam agendadas até o disparo automático rodar — em
produção, um **GitHub Actions agendado** chama o disparo a cada 15
minutos (ver `DEPLOY.md`, seção 7). Cada canal segue uma rampa de
aquecimento (limite diário de envios crescente conforme os dias de uso
do canal), para preservar a reputação do domínio/número.

### 5.6 Rastreio de abertura de e-mail

Todo e-mail enviado carrega um pixel de rastreio invisível — quando o
destinatário abre, o sistema registra automaticamente o horário da
abertura. A **taxa de abertura de e-mail** aparece nos indicadores do
painel administrativo, dando visibilidade de quem abriu (ou não) cada
prospecção sem precisar de nenhuma ação manual.

### 5.7 Reuniões e dossiê

Quando um decisor responde positivamente e uma reunião é proposta:

- **Horários propostos**: a tela mostra os horários sugeridos; o
  próprio lead também pode confirmar por um link público enviado a ele
  (sem precisar logar na plataforma) ou solicitar reagendamento.
- **Agendada → Marcar resultado**: depois da reunião, marque
  `realizada` ou `no-show`.
- **Confirmar qualificação**: para reuniões realizadas, confirme se foi
  uma reunião qualificada (sim/não) — isso alimenta o score de
  qualificação de futuras prospecções semelhantes.
- **Ver dossiê**: dossiê automático da reunião — dores levantadas,
  respostas do decisor, score de qualificação e a próxima ação
  recomendada.
- **Lembretes automáticos**: D-1 e H-2 antes do horário confirmado, um
  lembrete é enviado ao decisor pelo mesmo canal, reduzindo no-show.
- **Pesquisa de NPS**: alguns dias após a reunião (prazo configurável
  em Configuração), uma pesquisa de satisfação é disparada
  automaticamente por um link público — sem ação manual necessária.

Lembretes e NPS rodam no mesmo agendador que dispara as cadências (a
cada 15 minutos, ver `DEPLOY.md` seção 7) — nenhum dos dois depende de
alguém abrir a plataforma para acontecer.

---

## 6. Administração

Restrito a `super_admin` — gestão dos tenants assinantes da B2B ON.

- **Tenants**: lista todos os tenants; "Criar tenant" cadastra um
  cliente novo de uma vez (identificador, razão social, CNPJ, plano e
  o primeiro usuário admin).
- **Licenças**: para cada tenant, o plano atual, status
  (`ativa`/`suspensa`/`expirada`) e data de expiração — editável aqui.
  Suspender ou expirar uma licença bloqueia imediatamente o acesso do
  tenant a tudo além da Rede Social.
- **Planos**: catálogo dos planos comerciais (somente leitura na tela;
  alterar valores é uma operação de banco de dados, não de produto).
- **Convites**: convites de cadastro (usuário novo dentro de um tenant
  já cliente) e convites-vitrine (tenant novo, sem licença) gerados
  pelo próprio tenant.

---

## 7. Modelos de licença

### O que é uma licença

Cada tenant tem no máximo **uma licença** (`Licenca`), vinculada a um
**plano** (`Plano`) e com um status: `ativa`, `suspensa` ou `expirada`.
Só licença com status `ativa` libera os módulos pagos (CRM, MAP,
PREDATOR). **Um tenant sem nenhuma linha de licença** — caso do
convite-vitrine — fica automaticamente restrito à Rede Social; não
existe uma "flag" separada para isso, é a ausência da licença que gera
a restrição.

### O que é a "franquia"

A **franquia** é a cota mensal de contas que um tenant pode ativar em
cadências de prospecção. Ela é consumida **apenas no momento em que uma
conta entra numa cadência ativada** — nunca ao gerar uma lista de
contas, avaliar ou descartar contas. Isso significa:

- Gerar 500 contas de um ICP e nunca ativá-las em cadência **não**
  consome franquia.
- Ativar uma cadência com 30 contas novas consome 30 unidades da
  franquia do mês corrente.
- Reincluir a mesma conta numa cadência dentro do mesmo mês **não**
  consome de novo (idempotente por tenant + conta + mês).
- Se o lote a ativar ultrapassar o que resta da franquia, a ativação
  inteira é bloqueada (nada é consumido) — mas cadências já ativas
  continuam rodando normalmente, sem interrupção.
- A franquia zera e recomeça a cada mês civil.

O consumo/restante em tempo real aparece na tela de **Prospecção**.

### Planos padrão

| Plano | Franquia (contas/mês) | Máx. usuários | Preço mensal |
|---|---|---|---|
| POC | 50 | 3 | R$ 0 (gratuito) |
| Starter | 200 | 10 | R$ 490 |
| Professional | 800 | 25 | R$ 990 |
| Enterprise | 5.000 | 999 (na prática, ilimitado) | R$ 2.490 |

Esses valores são registros no banco (tabela `plano`), não constantes
fixas no código — podem ser ajustados comercialmente sem alteração de
software, e novos planos podem ser criados do mesmo jeito.

**"Máx. usuários"** é o número de contas de usuário (`Usuario`) que o
plano comporta dentro do tenant — é o limite pensado para dimensionar o
plano correto para o tamanho do time do cliente (ex.: POC serve para um
piloto de até 3 pessoas; Enterprise cobre praticamente qualquer time).

### O tier "vitrine" (sem licença)

Uma empresa que entra só pelo **convite-vitrine** (seção 3) nunca tem
uma linha de `Licenca` criada para o tenant dela — o que a torna, na
prática, um quinto "plano" de custo zero e acesso mínimo:

| | POC | Vitrine (sem licença) |
|---|---|---|
| Rede Social | ✓ | ✓ |
| CRM / MAP / PREDATOR | ✓ (franquia 50/mês) | ✗ |
| Custo | R$ 0 | R$ 0 |
| Como se torna cliente pago | — | Admin da B2B ON atribui um plano ao tenant em **Administração → Licenças** |

A diferença para o plano POC é que POC já é um cliente com franquia de
prospecção; o tier vitrine é puramente uma porta de entrada de
relacionamento — a empresa participa da rede, conhece os outros
módulos por dentro (o texto de boas-vindas do convite já menciona CRM,
MAP e PREDATOR), e o upgrade para um plano pago é uma decisão comercial
feita depois, sem precisar recriar a conta: basta o `super_admin`
atribuir uma licença ao tenant já existente.
