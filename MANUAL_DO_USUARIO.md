# Manual do Usuário — B2B ON

Guia funcional da plataforma B2B ON: o que cada módulo faz, como usar
no dia a dia e como funcionam os planos de licença. Para instalar/rodar
o projeto ou fazer deploy, veja [README.md](README.md) e
[DEPLOY.md](DEPLOY.md) — este documento é sobre o **uso** da plataforma
já em funcionamento.

## Sumário

1. [Conceitos gerais](#1-conceitos-gerais)
2. [CRM](#2-crm)
3. [Shoal](#3-shoal)
4. [MAP — Motor de Alta Performance](#4-map--motor-de-alta-performance)
5. [PREDATOR](#5-predator)
6. [Leads (clientes avulsos, sem ICP)](#6-leads-clientes-avulsos-sem-icp)
7. [Administração](#7-administração)
8. [Modelos de licença](#8-modelos-de-licença)

---

## 1. Conceitos gerais

### Tenant

Cada empresa que usa a B2B ON é um **tenant** — um espaço isolado de
dados (contas, negócios, mensagens, etc.). Um usuário sempre pertence a
exatamente um tenant e só enxerga os dados dele. A exceção deliberada é
o **Shoal**, onde tenants diferentes interagem entre si (perfis,
conexões, mensagens, posts) de forma controlada.

### Papéis de usuário

Cada usuário tem um papel (`papel`), que define o que ele pode fazer:

- **`user`** — uso normal do dia a dia: CRM, Prospecção, Cadências,
  Aprovações, Reuniões, Shoal — e o **MAP**, mas só das contas em
  que é o vendedor responsável (sua própria carteira).
- **`admin`** — tudo que `user` faz, mais gerar/revogar convites de
  colega para novos usuários do próprio tenant (**Admin → Convites**,
  seção [7](#7-administração)). No MAP, é o gestor:
  vê a carteira de todos os vendedores do tenant, com filtro por
  vendedor, e é quem atribui qual vendedor é responsável por cada conta.
  Se o tenant é `distribuidor`/`revendedor` (seção
  [7](#7-administração)), também enxerga — em **MAP** e em **Leads →
  Empresas** — a subárvore de sub-tenants abaixo dele, não só o próprio
  tenant.
- **`super_admin`** — reservado à equipe da própria B2B ON (CyberFort):
  além de tudo acima, enxerga a área de **Administração** (Tenants,
  Licenças, Planos). O MAP dele é outro: monitora a saúde de *todos os
  tenants assinantes* da B2B ON, não as contas de um tenant específico
  — ver seção 4 para a diferença entre os dois MAPs.

### Busca Global (Ctrl+K)

Em qualquer tela, `Ctrl+K` (ou o botão **Buscar** no topo do menu
lateral) abre uma busca única por empresa, oportunidade, proposta,
contato, cadência ou tenant (este último só pra quem administra
hierarquia — `admin` de distribuidor/revendedor ou `super_admin`).
Resultados agrupados por tipo, navegação por teclado (`↑`/`↓`/`Enter`).
Busca em qualquer conta do tenant, inclusive as que vieram de
prospecção via ICP — diferente das telas de **Leads**, que só cobrem
cadastros avulsos (ver seção [6](#6-leads-clientes-avulsos-sem-icp)).

### Entrando na plataforma

Existem dois jeitos de uma conta de usuário nascer — não confundir os
dois:

- **Convite de colega** (`admin`/`super_admin` gera em **Admin →
  Convites**, seção [7](#7-administração)): traz uma pessoa nova pra
  dentro do **seu próprio tenant** — já cliente pagante, acesso
  completo aos módulos que a licença cobre. Qualquer `admin` já pode
  gerar, com o papel `user` ou `admin`; só um `super_admin` pode gerar
  um convite que concede o papel `super_admin`.
- **Convidar empresa** (qualquer usuário gera na tela **Shoal**, seção
  [3](#3-shoal)): cria um **tenant novo e independente**, sem licença
  nenhuma — a empresa convidada entra só para participar do Shoal, sem
  virar cliente (a menos que seja um convite "gratuito", que já entrega
  o plano Teste — restrito a `admin`/`super_admin`). Veja a seção
  [8](#8-modelos-de-licença) para o que isso restringe na prática.

### O que cada tela mostra depende da licença

Quem não tem licença ativa só vê o **Shoal** no menu — é o único
módulo liberado por padrão. Todo o resto (CRM, Prospecção, Cadências,
Aprovações, Reuniões, MAP, Configuração) exige licença ativa; a API
recusa o acesso com uma mensagem clara se isso não for atendido.

---

## 2. CRM

Funil de vendas do próprio tenant — negociações com as contas que a
Prospecção (PREDATOR) gerou ou que entraram por outro canal.

- **Pipeline (Kanban)**: colunas = estágios do funil (ex.: Descoberta,
  Proposta, Negociação, Ganho, Perdido), cada uma com o total de
  negócios e valor. Arrastar/mover um negócio para outra coluna
  atualiza o estágio; um negócio pode ser criado direto informando a
  conta, nome do negócio e valor.
- **Editar Funil** (restrito a Admin/Super Admin): cria filas
  customizadas além das 5 padrão (nome + tipo aberto/ganho/perdido),
  renomeia qualquer fila existente, exclui uma fila (recusa se ela
  tiver negócios dentro, ou se for a última do tipo "aberto") e
  reordena as filas com as setas ▲▼.
- **Dashboard**: dois blocos alimentados pelo CRM —
  - **Funil de vendas**: quantidade de negócios por estágio (gráfico de
    barras) e taxa de conversão do período.
  - **Economia**: LTV médio, CAC, taxa de churn, novos clientes e
    cancelamentos no mês.
- **Ligação automática com o PREDATOR**: quando uma reunião de
  prospecção é confirmada, o CRM ganha automaticamente uma oportunidade
  vinculada à conta — não é preciso lançar isso manualmente.
- **Importar/exportar oportunidades (CSV)** — restrito a Admin/Super
  Admin, botão "Importar/exportar CSV" no topo do Pipeline:
  - **Exportar** baixa um CSV com todas as oportunidades do tenant
    (empresa, CNPJ, contato, valor, estágio, datas etc.) — útil pra
    levar o histórico a outra plataforma ao encerrar contrato, ou como
    backup.
  - **Importar** aceita colar o conteúdo de uma planilha ou selecionar
    um arquivo `.csv` — pensado pra clientes que chegam de outra
    plataforma já com histórico de negócios. O mapeamento de colunas é
    sugerido automaticamente (por nome de cabeçalho reconhecido) e pode
    ser ajustado na tela antes de confirmar; empresas e contatos já
    cadastrados (mesmo CNPJ, ou mesmo nome/e-mail) são reaproveitados,
    nunca duplicados. Linhas com um estágio que não existe no funil do
    tenant entram como erro (mostrado após a importação), sem impedir
    as demais linhas do arquivo de entrarem.
  - **Reimportação**: só é garantida sem duplicar se o arquivo tiver
    uma coluna de **ID externo** mapeada (o próprio ID do negócio na
    plataforma de origem, quando existir) — sem essa coluna, importar o
    mesmo arquivo duas vezes cria oportunidades duplicadas (a tela
    avisa isso antes de confirmar). Um CSV exportado pela própria B2B
    ON já vem com essa coluna preenchida, então reimportá-lo (ex.: após
    restaurar um backup) nunca duplica.

---

## 3. Shoal

Rede social B2B **entre tenants** da B2B ON — parceiros, fornecedores,
clientes de módulos diferentes se conectando, publicando e trocando
mensagens. É o único módulo acessível sem licença ativa (o nome é uma
tradução livre de "cardume": empresas nadando juntas, em rede).

### 3.1 Perfil e verificação

- **Meu perfil**: logo, capa, setor, porte, sede (cidade/UF), mercados,
  produtos/serviços, tecnologias, certificações e redes sociais — como
  sua empresa aparece para as outras.
- **Selo de verificação**: solicite com um e-mail corporativo (se o
  domínio bater com o site cadastrado, isso já ajuda na análise) — um
  `super_admin` da B2B ON revisa manualmente e aprova ou recusa em
  **Admin → Verificações** (seção [7](#7-administração)).

### 3.2 Diretório, conexões e mensagens

- **Diretório de empresas**: busca por nome/descrição, com filtros de
  setor, porte, mercado e "só verificadas".
- **Conectar**: pedido de conexão com aceite mútuo — só depois de
  aceita é possível trocar mensagens ou abrir uma Sala Corporativa.
  **Seguir** não exige aceite (unidirecional, útil só pra acompanhar
  posts de uma empresa sem virar conexão). **Bloquear**/**Desconectar**
  encerram a interação quando necessário.
- **Mensagens**: conversa 1:1 entre duas empresas conectadas.
- **Salas Corporativas**: espaço mais estruturado que a DM, com canais
  (Geral, e outros como Comercial/Técnico/Jurídico/Financeiro, ou um
  canal customizado) — útil quando a conversa entre duas empresas
  cresce além de uma DM simples. Um canal marcado como "interno" só
  aparece pra quem o criou, nunca pro outro lado.

### 3.3 Feed da Rede

- **Publicar um post**: legenda obrigatória, com foto(s) — uma ou
  várias, formando um **carrossel** navegável — ou um vídeo, e um link
  opcional. O botão **"Inserir Foto/Vídeo"** abre o seletor de arquivo.
- **Comentar**: comentário no post inteiro (não por foto do carrossel).
- **Reagir**: 9 emojis — curtir, chorar de rir, uau, triste, força
  (mãos unidas), interessante, oração, genial (lâmpada) e um "like"
  simples. Cada empresa tem só uma reação ativa por post (escolher
  outra troca a anterior, não soma).
- **Compartilhar**: republica o post no seu próprio feed, com um card
  mostrando o post original e quem publicou — igual a um "repost".

### 3.4 Necessidades da Rede

Publique o que sua empresa está procurando — categoria, título,
descrição, requisitos e faixa de orçamento — visível pra rede toda ou
só pras suas conexões (visibilidade escolhida ao publicar). Encerre ou
marque como "atendida" quando resolver. No lado do **PREDATOR**
(**Sinais de Oportunidade**, seção [5.11](#511-sinais-de-oportunidade)),
outras empresas com fit real pro que você publicou podem aparecer como
sugestão de match, com o motivo explicado.

### 3.5 Convidar empresa

Qualquer usuário do tenant pode gerar um link de convite (com validade
em horas, e um e-mail de destinatário opcional — preenchendo, o
convite já sai por e-mail automaticamente) para uma empresa de fora
entrar no Shoal. Copie o link e envie por fora da plataforma se
preferir; ao abrir, a pessoa preenche razão social, CNPJ (opcional),
nome, e-mail e senha, e um tenant novo é criado na hora — sem precisar
de nenhuma aprovação manual do seu lado. O convite pode ser revogado
enquanto estiver "disponível" (ainda não usado).

A opção **"Convite gratuito"** (pula pagamento, cria a conta já no
plano Teste sem prazo de expiração) é restrita a `admin`/`super_admin`
— pensada só pra demonstração, não pra cliente pagante de verdade. Não
confundir com o **convite de colega** (seção [7](#7-administração)):
este aqui cadastra uma **empresa nova**, com tenant e licença próprios;
aquele traz uma pessoa pro **seu próprio** tenant.

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
| `admin` (gestor) | Todas as contas do próprio tenant, de todos os vendedores, com filtro por vendedor. Se o tenant é `distribuidor`/`revendedor`, também a subárvore de sub-tenants abaixo dele (seletor "Toda a hierarquia"). |
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
- **Seletor "Toda a hierarquia"** (só para `admin` de tenant
  `distribuidor`/`revendedor`, ou `super_admin`): por padrão, o ranking
  já mostra as contas do próprio tenant **mais** todos os sub-tenants
  abaixo dele, com uma coluna extra indicando de qual empresa é cada
  conta. Selecionar um tenant específico no seletor restringe a visão
  só àquela empresa (e à subárvore dela) — útil pra revisar a carteira
  de um Revendedor/Cliente específico sem misturar com o resto. O
  filtro por vendedor some quando um tenant específico é selecionado
  (o cadastro de vendedores é sempre do próprio tenant logado).
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
  execução **consome franquia mensal** (ver seção 8).
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
   `rascunho`. Num toque, é possível marcar **teste A/B** (exclusivo do
   plano Professional ou superior — nos demais planos a opção aparece
   bloqueada) pra comparar duas variações de texto no mesmo passo. Uma
   cadência aceita **no máximo 1 toque de WhatsApp**, sempre com um
   template aprovado selecionado (ver seção 5.5 — o motivo é a janela de
   24h da Meta, que nenhum toque agendado pra depois tem garantia de
   encontrar aberta). O canal WhatsApp fica desabilitado no seletor de
   qualquer outro toque assim que um já estiver usando esse canal.
2. Por padrão, uma resposta do decisor **não cancela mais os outros
   toques** da cadência — a nutrição por e-mail/LinkedIn continua
   normalmente. Marque a opção **"Parar esta cadência automaticamente
   se o cliente responder"** (na criação, ou depois no cabeçalho da
   cadência) se preferir o comportamento antigo — cancelar tudo que
   estiver pendente, em qualquer canal, assim que o decisor responder.
   Alternativamente, cancele manualmente um toque específico de um
   contato: em qualquer tela que abre a ficha da conta (Prospecção,
   Kanban, Leads), expanda **"Mensagens agendadas"** no card do decisor
   e use **"✕ Cancelar este envio"** na mensagem que não deve mais sair
   — os demais toques daquele mesmo contato continuam agendados.
3. **Gerar mensagens para um lote**: com a cadência em rascunho,
   escolha um ICP e marque as contas — a IA gera o texto de cada
   mensagem de cada toque, respeitando oferta/tom/restrições. Contas
   sem decisor mapeado ficam de fora (é preciso mapear um decisor
   antes). As mensagens geradas vão para a **fila de Aprovação**, e a
   cadência muda para `aguardando_aprovacao`.
4. **Ativar cadência**: depois que a fila de aprovação está revisada,
   ativar a cadência (`ativa`) faz os envios entrarem na fila de envio
   real, respeitando o agendamento de cada toque. É neste momento que a
   franquia é consumida para as contas novas do lote (ver seção 8).

### 5.4 Fila de Aprovação

Toda mensagem que a IA gera passa por aqui antes de sair — é o "mediante
aprovação" do PREDATOR.

- Lista mensagens pendentes, com filtro por canal — inclui também as já
  **rejeitadas** (filtro de status), com a opção **"Aprovar mesmo
  assim"** pra destravar uma cadência que ficaria parada pra sempre se
  a única mensagem daquele toque tivesse sido rejeitada por engano.
- **Editar**: o texto é editável antes de aprovar.
- **Aprovar** / **Rejeitar**: individual, ou "Aprovar todas" para o
  lote inteiro visível no filtro atual.
- Só mensagens aprovadas entram na fila de envio.
- **Auto-aprovação** (exclusivo do plano Enterprise): em
  **Configuração**, é possível marcar um template de WhatsApp como
  auto-aprovado — mensagens geradas com aquele template pulam a fila e
  vão direto pro envio, sem revisão manual. Pensado pra fluxos já
  validados e de alto volume; nos demais planos essa opção fica
  bloqueada.

### 5.5 WhatsApp Business — configuração obrigatória por conta

O canal WhatsApp **não é compartilhado entre clientes da B2B ON**: cada
tenant configura a própria conta Meta em **Configuração → WhatsApp
Business**, com número e token próprios. Não existe um número "da
CyberFort" usado por todo mundo — se o seu tenant não tiver essa
configuração feita, o toque de WhatsApp das suas cadências simplesmente
nunca sai (silenciosamente, sem erro na tela).

**Passo a passo para configurar:**

1. Crie (ou reutilize) um app em [developers.facebook.com](https://developers.facebook.com/apps),
   adicionando o produto **WhatsApp** a ele.
2. No painel do app, em **WhatsApp → Configuração da API**, anote o
   **Identificação do número de telefone** (`phone_number_id`) e o
   **WhatsApp Business Account ID** (`business_account_id`).
3. Gere um **token de acesso permanente**: em **Configurações da
   empresa → Usuários do sistema**, crie (ou reaproveite) um usuário do
   sistema com acesso ao app e à conta do WhatsApp, e gere um token para
   ele (sem esse passo, o token temporário do painel expira em poucas
   horas).
4. Cole `phone_number_id`, `business_account_id` e o token gerado em
   **Configuração → WhatsApp Business**, na B2B ON. As credenciais ficam
   criptografadas no banco.

**Por que o toque de WhatsApp é sempre via template, com botão de
redirecionamento:**

A Meta exige um **modelo de mensagem (template) aprovado** para qualquer
mensagem de WhatsApp enviada a um número que **nunca falou com a sua
conta antes** (ou que já passou de 24h desde a última resposta dele) —
essa regra é puramente mecânica (contada em horas desde a última
mensagem do contato), sem exceção de contexto: mesmo um retorno que o
próprio cliente pediu ("me chama semana que vem") conta como "frio" de
novo se passar mais de 24h. Por isso uma cadência aceita **só 1 toque de
WhatsApp**, e ele é sempre um template — não existe mais um segundo
toque de WhatsApp "de texto livre" agendado pra depois, porque nenhuma
data futura tem garantia de encontrar a janela de 24h aberta.

Pra não perder a conversa por causa dessa limitação, o template usa um
**botão de redirecionamento** (`https://wa.me/{{1}}`) que leva o
contato direto pro **WhatsApp pessoal do vendedor responsável pela
conta** (app do celular ou WhatsApp Web) — a partir daí a conversa
acontece no aplicativo de verdade, sem nenhuma restrição de janela ou
template, exatamente como qualquer contato feito fora da plataforma. O
custo dessa troca: as mensagens trocadas por lá **não ficam registradas
automaticamente no CRM** — registre manualmente na aba de Atividade da
conta quando fizer sentido, do mesmo jeito que já se faz para qualquer
outro contato feito fora do sistema.

**Passo a passo:**

1. Em **Meta for Developers → WhatsApp → Modelos de mensagem**, crie um
   modelo (categoria "Marketing" ou "Utilidade"), escreva o texto e
   adicione um botão do tipo **"Visitar site"** com **URL dinâmica**
   `https://wa.me/{{1}}` (a variável `{{1}}` do botão é preenchida pela
   B2B ON, na hora do envio, com o WhatsApp pessoal do vendedor). Envie
   para aprovação da Meta — costuma levar de minutos a poucas horas.
2. Cada vendedor cadastra o **próprio número de WhatsApp** em **Meu
   Perfil** (clique no seu nome/avatar no canto inferior do menu) — é
   esse número que o botão do template usa. Sem ele preenchido, o botão
   não leva a lugar nenhum; um aviso aparece no topo da tela para quem
   tem conta(s) atribuída(s) e ainda não cadastrou o próprio número.
3. Ao criar o toque de WhatsApp de uma cadência (seção 5.3), selecione o
   **template aprovado** no campo correspondente do toque — a lista já
   vem sincronizada com os templates aprovados na Meta, sem precisar
   digitar nada; o campo é obrigatório, não é possível salvar o toque de
   WhatsApp sem um template. Se a cadência já existia antes do template
   ser aprovado, não é preciso recriá-la: a tela de Cadências mostra um
   aviso "sem template" ao lado do toque de WhatsApp sem um definido,
   com um seletor pra escolher o template ali mesmo.

### 5.6 Disparo e rampa de aquecimento

Mensagens aprovadas ficam agendadas até o disparo automático rodar — em
produção, um **GitHub Actions agendado** chama o disparo a cada 15
minutos (ver `DEPLOY.md`, seção 7). Cada canal segue uma rampa de
aquecimento (limite diário de envios crescente conforme os dias de uso
do canal), para preservar a reputação do domínio/número.

### 5.7 Rastreio de abertura de e-mail

Todo e-mail enviado carrega um pixel de rastreio invisível — quando o
destinatário abre, o sistema registra automaticamente o horário da
abertura. A **taxa de abertura de e-mail** aparece no **Relatório de
Entrega** (seção 5.9), dando visibilidade de quem abriu (ou não) cada
prospecção sem precisar de nenhuma ação manual.

### 5.8 Reuniões e dossiê

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

### 5.9 Relatório de Entrega e proteção contra bounce de e-mail

Em **Predator → Relatório de Entrega**: entregabilidade de e-mail e
taxa de resposta por canal — o que a plataforma consegue de fato medir
(WhatsApp e LinkedIn não têm confirmação de entrega/leitura rastreada,
só a taxa de resposta é medida pra eles).

**Proteção automática contra bounce (só para e-mail):** a B2B ON
monitora, numa janela de 7 dias, a taxa de e-mails que **quicaram**
(endereço inválido, caixa cheia, bloqueado pelo provedor do
destinatário) ou foram marcados como spam. Se essa taxa passar de 5%
(bounce) ou 0,1% (spam), o canal de e-mail do seu tenant é **pausado
automaticamente** — nenhuma campanha ou cadência de e-mail nova pode
ser ativada, e os toques de e-mail já agendados ficam parados, até você
resolver. Isso existe pra proteger a reputação do domínio e evitar que
os e-mails de todo mundo passem a cair em SPAM.

**Como resolver:**

1. No Relatório de Entrega, a seção "Contatos com e-mail rejeitado"
   lista exatamente quem causou cada bounce — nome, conta, e-mail e o
   motivo reportado pelo provedor.
2. Pra cada contato: **"Editar e-mail"** abre a ficha da conta pra
   corrigir um endereço digitado errado, ou **"Excluir contato"**
   suprime o contato (ele para de receber qualquer mensagem, de
   qualquer cadência — mesma supressão usada no opt-out, não apaga o
   histórico).
3. Depois de corrigir/excluir os contatos problemáticos, clique em
   **"Reativar canal"** — o bloqueio não expira sozinho, é sempre
   manual, feito só depois que a causa foi tratada.

Essa proteção só vale pra quem usa o e-mail compartilhado da B2B ON
(SendGrid) — contas com **SMTP próprio** configurado em Configuração →
E-mail (SMTP) não passam por esse rastreio de bounce, já que o
provedor deles não avisa a B2B ON quando um e-mail quica.

### 5.10 Regras Aprendidas

Fecha o loop entre "a IA errou/o vendedor corrigiu" e "a próxima
geração já nasce melhor":

- **Correções recentes**: lista as últimas mensagens editadas ou
  rejeitadas na Fila de Aprovação, com o antes/depois (edição) ou o
  motivo (rejeição). **"✨ Sugerir com IA"** pede à IA um texto de regra
  a partir daquela correção específica — a sugestão só entra no campo
  de texto, quem decide se cria a regra (e pode editar o texto antes)
  é sempre a pessoa.
- **Cadastrar regra**: texto livre (ex.: "nunca usar a palavra
  'sinergia'"), com escopo opcional por ICP/Oferta/canal — nulo em
  qualquer campo significa "vale pra todos". Toda regra ativa entra
  automaticamente no prompt da próxima geração de mensagem de cadência
  que bater no escopo.
- **Padrões da Empresa**: ticket médio, ciclo médio de venda e motivo
  de perda mais comum, calculados a partir dos seus próprios negócios
  ganhos/perdidos — sempre mostrado junto do tamanho da amostra (nunca
  como fato isolado; com poucos negócios, o padrão nem aparece).

### 5.11 Sinais de Oportunidade

Cruza o Shoal (rede social) com o CRM/ICP pra apontar oportunidades
reais, sempre com o motivo explicado — nunca um número opaco:

- **Fit de ICP**: quais empresas do Shoal batem com um ICP seu
  (segmento/UF/porte), com os critérios que bateram e os dados que
  faltam pra ter mais confiança.
- **Matches de Necessidade**: quando outra empresa publica uma
  Necessidade da Rede (seção [3.4](#34-necessidades-da-rede)) que o seu
  perfil/oferta pode atender, ou quando uma Necessidade sua encontra um
  fornecedor em potencial.
- **Riscos de pipeline**: negócios abertos parados há muitos dias, ou
  sem nenhum decisor com papel de comprador confirmado.
- **Atribuição de receita**: quanto do pipeline/receita ganha veio de
  um sinal originado na rede — e sugestões de expansão (uma Conta com
  negócio ganho que ainda não comprou uma Oferta ativa sua).

### 5.12 Agente Corporativo

Um assistente de IA que responde, **sempre sob revisão humana**,
perguntas que **outras empresas do Shoal** fazem sobre a sua — baseado
só na sua Oferta ativa, Perfil da Empresa e FAQ cadastrados (nunca
inventa além disso; sem essas informações cadastradas, a pergunta cai
numa resposta padrão de "sem informação suficiente").

- **Modo**: desligado (padrão) / interno (só você testa, nada é
  exposto à rede) / assistido (outra empresa pode perguntar; toda
  resposta fica pendente até você aprovar, editar ou recusar).
- **Testar seu agente**: simula uma pergunta e mostra o rascunho de
  resposta + as evidências usadas, sem persistir nada.
- **Perguntas recebidas**: fila de perguntas de outras empresas
  aguardando revisão — aprovar (com edição opcional) ou recusar com
  motivo.
- **Minhas perguntas**: o que você perguntou ao agente de outras
  empresas conectadas, e as respostas recebidas.

---

## 6. Leads (clientes avulsos, sem ICP)

Cadastro manual de empresas conquistadas fora do PREDATOR — indicação,
evento, contato pessoal — que não passam pelo recorte de segmento/
porte/dor de nenhum ICP. Duas telas no menu **Leads**:

- **Empresas**: lista as contas cadastradas manualmente (**+ Nova
  empresa**: nome, CNPJ opcional, domínio opcional, segmento, porte,
  UF), com busca por nome e filtro por vendedor. Pra `admin` de tenant
  `distribuidor`/`revendedor` (ou `super_admin`), ganha o mesmo seletor
  "Toda a hierarquia" do MAP — por padrão mostra os leads do próprio
  tenant **mais** os de toda a subárvore de sub-tenants, com uma coluna
  indicando de qual tenant é cada empresa; selecionar um tenant
  específico restringe a visão só a ele.
- **Contatos**: lista os decisores cadastrados nessas empresas
  avulsas (nome, cargo, e-mail, telefone, empresa vinculada), com
  **+ Novo contato** (vinculado a uma empresa existente ou a uma nova,
  criada na hora) e busca por nome/cargo/empresa. Diferente da tela de
  Empresas, esta não tem seletor de hierarquia.

**Importante**: estas duas telas só mostram contas **sem ICP e sem
Lista de Prospecção** — uma conta gerada por um ICP ativo (seção 5.2)
ou importada numa Lista de Prospecção aparece no **CRM**/**Prospecção**,
não aqui, mesmo que já tenha decisores mapeados. Isso evita duplicar a
mesma empresa em dois lugares. Pra ver **todas** as contas do tenant
(com ou sem ICP) num só lugar, use o **MAP** (seção 4) ou a **Busca
Global** (seção [1](#1-conceitos-gerais)).

---

## 7. Administração

Gestão dos tenants assinantes da B2B ON. **Tenants**/**Licenças**/
**Relatórios** são visíveis pra `super_admin` **e** pra `admin` de um
tenant `distribuidor`/`revendedor` (escopados à própria subárvore);
**Convites** é visível pra **qualquer** `admin`/`super_admin` (é
escopado ao próprio tenant, sem depender de hierarquia); **Planos** e
**Verificações** são exclusivos de `super_admin` (operação global,
cross-tenant).

### Hierarquia de tenants (Distribuidor → Revendedor → Cliente)

Todo tenant tem um `tipo`: `distribuidor`, `revendedor` ou `cliente`
(o padrão), e opcionalmente um tenant pai (`tenant_pai_id`), formando
uma árvore rasa (3 níveis sob a CyberFort). Quem cria um tenant sob si
mesmo (na tela **Tenants** ou pela API de parceiros — ver
`docs/api-parceiros.md`) só pode fazer isso um nível abaixo do próprio
tipo (distribuidor cria revendedor, revendedor cria cliente);
`super_admin` cria de qualquer tipo, em qualquer ponto da árvore. Os
rótulos exibidos pra cada nível (por padrão "Distribuidor"/
"Revendedor"/"Cliente") são configuráveis por tenant, útil pra quem
usa nomenclatura própria (ex.: "Master"/"Vendedor"/"Cliente").

- **Tenants**: lista os tenants visíveis (todos, pra `super_admin`; a
  própria subárvore, pra admin de distribuidor/revendedor). "Criar
  tenant" cadastra um cliente novo de uma vez (identificador, razão
  social, CNPJ, plano e o primeiro usuário admin).
- **Licenças**: para cada tenant visível, o plano atual, status
  (`ativa`/`suspensa`/`expirada`) e data de expiração — editável aqui.
  Suspender ou expirar uma licença bloqueia imediatamente o acesso do
  tenant a tudo além do Shoal (sujeito à carência descrita na
  seção [8](#8-modelos-de-licença)).
- **Relatórios** (visão do distribuidor/revendedor sobre a própria
  subárvore): dashboard com tenants ativos por nível, novas ativações,
  licenças suspensas, franquia consumida, receita e churn no período,
  com envio periódico por e-mail configurável (diário/semanal/mensal).
  O disparo automático por **webhook** desse relatório pro sistema do
  próprio distribuidor é exclusivo do plano Professional ou superior
  (seção [8](#8-modelos-de-licença); ver também `docs/api-parceiros.md`).
- **Integrações** (exclusivo de `admin` de tenant `tipo="distribuidor"`):
  gera a chave de API usada pra provisionar/gerenciar a própria árvore
  por fora do painel (sistema de billing/ERP do distribuidor), e
  configura a URL de webhook que recebe os eventos da árvore —
  detalhes completos em `docs/api-parceiros.md`.
- **Planos** (exclusivo de `super_admin`): CRUD completo — criar,
  editar e (dentro do possível) remover planos comerciais direto na
  tela, incluindo franquia, limite de usuários, preço, os dois limites
  de enriquecimento semanal, os recursos exclusivos por plano e as
  retenções (ver seção [8](#8-modelos-de-licença)) — não depende mais
  de alteração direta no banco de dados.
- **Convites** (qualquer `admin`/`super_admin`): convida um colega pro
  **seu próprio tenant**, com o papel `user` ou `admin` — só um
  `super_admin` pode gerar um convite que concede o papel `super_admin`
  (trava de segurança: sem ela, qualquer admin comum poderia se
  auto-elevar a um papel global). Não confundir com "Convidar empresa"
  no Shoal (seção [3.5](#35-convidar-empresa)), que cadastra uma
  empresa nova com tenant/licença próprios.
- **Verificações** (exclusivo de `super_admin`): fila de pedidos de
  selo de verificação de perfil do Shoal (seção
  [3.1](#31-perfil-e-verificação)) — aprova ou recusa, com os sinais
  automáticos (domínio do e-mail confere com o site, CNPJ encontrado na
  Receita Federal) visíveis pra ajudar na decisão.

---

## 8. Modelos de licença

### O que é uma licença

Cada tenant tem no máximo **uma licença** (`Licenca`), vinculada a um
**plano** (`Plano`) e com um status: `ativa`, `suspensa` ou `expirada`.
Só licença com status `ativa` libera os módulos pagos (CRM, MAP,
PREDATOR). **Um tenant sem nenhuma linha de licença** — caso do
convite-vitrine — fica automaticamente restrito ao Shoal; não
existe uma "flag" separada para isso, é a ausência da licença que gera
a restrição.

### Carência de 3 dias e cobrança automática

A suspensão por falta de pagamento **não é imediata** no vencimento —
existe uma carência de 3 dias, pensada pro tempo de compensação de
boleto bancário (Mercado Pago) e pra não penalizar quem paga por cartão
perto da virada do dia:

- **3 dias antes do vencimento**: e-mail único avisando que a
  mensalidade está próxima de vencer.
- **A partir do vencimento** (enquanto durar a carência): um e-mail
  diário de lembrança, até o pagamento ser confirmado ou a carência se
  esgotar.
- **"Já fiz o pagamento"**: se o usuário for suspenso mas já tiver
  pago (ainda em compensação), qualquer `admin`/`super_admin` do tenant
  vê um aviso na tela com um botão pra se autodeclarar pagador — o
  acesso volta **na hora**, sem esperar confirmação do Mercado Pago.
  Essa autodeclaração abre uma carência própria de mais 3 dias: se o
  pagamento realmente não for confirmado até lá, a licença é suspensa
  de novo.
- **Confirmação do pagamento**: assim que o Mercado Pago confirma
  (webhook), a licença é reativada automaticamente por 30 dias e um
  e-mail de agradecimento é enviado — independente de ter havido
  autodeclaração no meio do caminho.
- **Primeiro login**: todo usuário recebe um e-mail de boas-vindas
  no primeiro acesso, com FAQ e contato do suporte
  (`suporte@cyberfort.com.br`).

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
| Teste | 200 | 10 | R$ 0 (cortesia, só por convite) |
| Starter | 200 | 10 | R$ 490 |
| Professional | 800 | 25 | R$ 990 |
| Enterprise | 5.000 | 999 (na prática, ilimitado) | R$ 2.490 |

Esses valores são registros no banco (tabela `plano`), não constantes
fixas no código — podem ser ajustados comercialmente sem alteração de
software (tela **Admin → Planos**, exclusiva de `super_admin`), e
novos planos podem ser criados do mesmo jeito.

**"Máx. usuários"** é o número de contas de usuário (`Usuario`) que o
plano comporta dentro do tenant — é o limite pensado para dimensionar o
plano correto para o tamanho do time do cliente (ex.: POC serve para um
piloto de até 3 pessoas; Enterprise cobre praticamente qualquer time).

**Plano "Teste"** espelha o Starter em franquia/usuários, mas é
gratuito e nasce **sem** cobrança nem data de expiração — só é
atribuído por convite de um `admin`/`super_admin` (não aparece como
opção de autoatendimento no cadastro), pensado pra pilotos internos ou
avaliação comercial sem risco de suspensão automática.

### Recursos exclusivos por plano

Além do volume (franquia/usuários), alguns recursos são um gancho de
upgrade — bloqueados nos planos mais baixos independente de quanto a
franquia ainda tenha sobrado. O plano **Teste** espelha o Starter aqui
também (nenhum dos recursos abaixo):

| Recurso | POC / Starter / Teste | Professional | Enterprise |
|---|---|---|---|
| Teste A/B em cadências | ✗ | ✓ | ✓ |
| Auto-aprovação de mensagens | ✗ | ✗ | ✓ |
| Webhook automático no relatório periódico | ✗ | ✓ | ✓ |
| API de parceiros (provisionamento/billing) | ✗ | ✓ | ✓ |
| Criar sub-tenants (hierarquia) | ✗ | ✓ | ✓ |
| Retenção de relatórios / auditoria | 30 / 90 dias | 90 / 365 dias | sem limite |

A UI mostra um cadeado nas opções bloqueadas em vez de simplesmente
escondê-las — o bloqueio de verdade é sempre revalidado no backend, não
depende só do que a tela mostra.

### O tier "vitrine" (sem licença)

Uma empresa que entra só pelo **convite-vitrine** (seção 3) nunca tem
uma linha de `Licenca` criada para o tenant dela — o que a torna, na
prática, um quinto "plano" de custo zero e acesso mínimo:

| | POC | Vitrine (sem licença) |
|---|---|---|
| Shoal | ✓ | ✓ |
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
