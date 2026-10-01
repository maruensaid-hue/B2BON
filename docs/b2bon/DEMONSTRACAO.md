# Ambiente de demonstração (D-082)

Link público para os representantes mostrarem o B2B ON a clientes, sem login nem senha reais.

- **Link**: `https://b2bon.onrender.com/demo` — também no botão **DEMO** do rodapé da tela de login.
- O botão fica sempre visível; com a demonstração desligada no servidor, o link mostra "A demonstração não está habilitada".

## Como funciona

- Cada acesso ao link cria um **ambiente próprio**, já preenchido, que **expira em 8 horas** e depois é apagado. Vários
  representantes podem demonstrar ao mesmo tempo: o que um faz (mover um negócio, aprovar uma mensagem, avaliar uma
  proposta) não aparece para o outro.
- A sessão entra como **Marina Costa, gestora comercial** da empresa fictícia **Atlas Soluções Industriais**, com
  todos os módulos: CRM, MAP, PREDATOR, Bid Intelligence, Public Procurement e Strategic Sourcing.
- Uma faixa no topo avisa que é demonstração e mostra a hora em que expira; **"Nova demonstração"** abre outro ambiente
  limpo (útil para começar a próxima apresentação do zero).

## O que vem preenchido (tudo fictício, aplicações reais)

| Área | Conteúdo |
|---|---|
| Equipe | gestora, executivo de contas, executiva de setor público e SDR |
| ICP e ofertas | indústria Sul/Sudeste e municípios; 4 ofertas (manutenção preditiva, gestão de ativos, eficiência energética, licença setor público) |
| Contas e contatos | 15 empresas (indústrias, saneamento, prefeitura, hospital), decisores com cargo, e-mail e telefone fictícios; leads manuais |
| Funil (CRM) | 14 negócios em Descoberta, Proposta, Negociação, Ganho e Perdido, com valores, probabilidade, propostas em PDF e histórico de atividades |
| Prospecção | lista de prospecção, 3 cadências (e-mail, LinkedIn, WhatsApp), mensagens enviadas e **fila de aprovação** com pendências, campanha em rascunho |
| Agenda | reuniões agendadas (próximos dias, com link), realizadas (qualificadas e não), no-show |
| MAP | clientes com sinais de saúde (elogio, ticket, reclamação, reunião remarcada), NPS respondido, necessidades mapeadas nas oportunidades |
| Licitações | Pregão Eletrônico em análise, Pregão SRP com decisão GO, RFP privado com proposta enviada, licitações **futuras** do PCA (concorrência e dispensa), NO-GO justificado e pregão ganho — cada um com requisitos (habilitação, atestado, SLA, garantia) |
| Compras públicas | órgão, unidade, PCA do próximo ano, demandas, pregão em pesquisa de preços (3 fontes), fornecedores e contratos (um vencendo em 35 dias) |
| Strategic Sourcing | RFP de notebooks com 3 fornecedores, propostas e avaliação por requisito (comparação pronta); RFQ de manutenção predial em rascunho |
| IA | 5.000 créditos de IA próprios da demonstração (expiram com ela) |

## O que a demonstração não faz (proteções)

- **Nada sai de verdade**: e-mails e WhatsApp de cadências e campanhas usam provedores simulados.
- **Nenhum dado real entra**: a Rede Social, a inteligência de rede, indicações e oportunidades entre empresas ficam
  fora (mostrariam clientes reais). A empresa fictícia não aparece no diretório da rede.
- **Nada que gere custo ou acesso**: pagamento e compra de créditos, criação de usuários e convites, credenciais
  (SMTP, WhatsApp, chaves de API, webhooks, integrações de CRM, LinkedIn), coleta externa do PNCP, descoberta de
  fornecedores na rede e acesso ao portal do fornecedor respondem "Indisponível na demonstração".
- **Administração da plataforma** (comissões, governo, representantes, FinOps, MAP Performance) não aparece.
- **Limites**: até 60 demonstrações abertas ao mesmo tempo e 20 novas por hora por endereço IP.

## Passo a passo para publicar

1. **Atualizar o site**: o código já está no `master` (o Render publica a API `b2bon-api` e o site `B2BON` sozinho a
   cada atualização do `master`). Confira em Render → serviço → Events que o último deploy terminou.
2. **Ligar a demonstração na API**: Render → serviço **b2bon-api** → **Environment** → **Add Environment Variable**:
   - `DEMO_HABILITADA` = `true`
   - (opcional) `DEMO_TTL_HORAS` (padrão 8), `DEMO_MAX_SESSOES_ATIVAS` (60), `DEMO_SESSOES_POR_IP_HORA` (20),
     `DEMO_CREDITOS_IA` (5000).
   Salve; o Render reinicia o serviço.
3. **Testar**: abra `https://b2bon.onrender.com/demo` numa janela anônima — em poucos segundos aparece o painel com a
   faixa "Ambiente de demonstração". Na tela de login deve aparecer "Ver demonstração (sem login)".
4. **Divulgar aos representantes**: envie o link `https://b2bon.onrender.com/demo`. Cada clique abre um ambiente novo; o
   representante pode deixar a aba aberta durante a reunião (vale 8 horas) e usar "Nova demonstração" para recomeçar.
5. **No site institucional** (opcional): um botão "Ver demonstração" apontando para o mesmo link.
6. **Limpeza**: automática — a rotina horária (`/cron/creditos-ia`) apaga os ambientes vencidos, e cada nova
   demonstração também apaga até 5 vencidos antes de começar.

**Desligar**: remova `DEMO_HABILITADA` (ou mude para `false`). O link passa a mostrar "A demonstração não está
habilitada" e o botão some da tela de login; os ambientes existentes expiram sozinhos.

## Dúvidas comuns

- *"Muitas demonstrações abertas agora"*: o limite de sessões simultâneas foi atingido — aumente
  `DEMO_MAX_SESSOES_ATIVAS` ou aguarde as mais antigas expirarem.
- *A sessão caiu*: passou o prazo (8 h). Abra o link de novo.
- *Funções de IA* (análise de edital, avaliação de propostas, resumo de reunião) usam os créditos da demonstração; ao
  acabarem, a tela mostra o aviso normal de créditos insuficientes.
