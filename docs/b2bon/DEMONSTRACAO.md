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

## Segurança (D-083)

- **Negação por padrão**: a sessão de demonstração só acessa as telas de produto (dados do próprio ambiente fictício).
  Administração da plataforma, usuários, convites, credenciais, integrações, pagamentos, rede de empresas, LGPD, API de
  parceiros e qualquer rota nova respondem "Indisponível na demonstração".
- **Nada sai da plataforma**: e-mail, WhatsApp, agenda, robô de reunião, enriquecimento de contatos, busca web,
  pagamento, acesso a sites externos e o grafo são simulados na demonstração. Só a IA é real, limitada a 5.000 créditos
  por ambiente.
- **Nada de dados reais entra**: cada sessão é um tenant próprio e isolado; outros clientes, a rede de empresas e as
  visões da plataforma são inalcançáveis; a empresa fictícia não aparece no diretório.
- **Sem senha a ser roubada**: os usuários fictícios não têm senha e os e-mails usam um domínio que nunca entrega; o
  acesso é um token assinado que vale só para aquele ambiente e expira com ele.
- **Contra abuso**: 10 demonstrações novas por hora por endereço IP real, 120 por hora no total, 60 abertas ao mesmo
  tempo; ambientes vencidos são apagados sozinhos.
- **Interruptor**: desligar `DEMO_HABILITADA` derruba na hora todas as sessões de demonstração abertas.

## Passo a passo para publicar

1. **Atualizar o site**: o código já está no `master` (o Render publica a API `b2bon-api` e o site `B2BON` sozinho a
   cada atualização do `master`). Confira em Render → serviço → Events que o último deploy terminou.
2. **Ligar a demonstração na API**: Render → serviço **b2bon-api** → **Environment** → **Add Environment Variable**:
   - `DEMO_HABILITADA` = `true`
   - (opcional) `DEMO_TTL_HORAS` (padrão 8), `DEMO_MAX_SESSOES_ATIVAS` (60), `DEMO_SESSOES_POR_IP_HORA` (10),
     `DEMO_SESSOES_POR_HORA` (120),
     `DEMO_CREDITOS_IA` (5000).
   Salve; o Render reinicia o serviço.
3. **Testar**: abra `https://b2bon.onrender.com/demo` numa janela anônima — em poucos segundos aparece o painel com a
   faixa "Ambiente de demonstração". O botão **DEMO** no rodapé da tela de login leva ao mesmo link.
4. **Divulgar aos representantes**: envie o link `https://b2bon.onrender.com/demo`. Cada clique abre um ambiente novo; o
   representante pode deixar a aba aberta durante a reunião (vale 8 horas) e usar "Nova demonstração" para recomeçar.
5. **No site institucional** (opcional): um botão "Ver demonstração" apontando para o mesmo link.
6. **Limpeza**: automática — a rotina horária (`/cron/creditos-ia`) apaga os ambientes vencidos, e cada nova
   demonstração também apaga até 5 vencidos antes de começar.

**Desligar**: remova `DEMO_HABILITADA` (ou mude para `false`). O link passa a mostrar "A demonstração não está
habilitada" (o botão DEMO continua no rodapé do login) e as sessões abertas caem na hora.

## Dúvidas comuns

- *"Muitas demonstrações abertas agora"*: o limite de sessões simultâneas foi atingido — aumente
  `DEMO_MAX_SESSOES_ATIVAS` ou aguarde as mais antigas expirarem.
- *A sessão caiu*: passou o prazo (8 h). Abra o link de novo.
- *Funções de IA* (análise de edital, avaliação de propostas, resumo de reunião) usam os créditos da demonstração; ao
  acabarem, a tela mostra o aviso normal de créditos insuficientes.
