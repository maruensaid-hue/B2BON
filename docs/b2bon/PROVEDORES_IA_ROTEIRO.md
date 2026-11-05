# Provedores de IA adicionais: comparação e roteiro de contas

Base técnica e fontes: [PROVEDORES_IA.md](PROVEDORES_IA.md) (documentações oficiais conferidas em 2026-10-20; revalidar antes de ativar).

## Para que servem

Hoje toda a IA do B2B ON roda na **Anthropic (Claude)**. Os provedores adicionais **não substituem** o Claude: entram só como
**reserva (fallback)** quando a Anthropic falha (fora do ar, limite, erro). O código já está pronto e testado com simulação; nenhum foi
ligado. Sem eles, quando a Anthropic cai, a plataforma mostra erro claro e retoma sozinha depois.

**Pergunta de negócio:** vale ter reserva antes de faturar? Minha leitura: **um provedor gratuito basta** para começar, e só para as
tarefas que usam dado público (editais, normalização de texto). Dado de cliente (CRM, mensagens, contatos) fica só no Claude até haver
avaliação de LGPD. Restringir a reserva a essas tarefas exige um ajuste pequeno no código (ver o fim deste documento).

## Comparação

| | Groq | Cloudflare Workers AI | OpenRouter (modelos `:free`) | Google Gemini (gratuito) |
|---|---|---|---|---|
| Custo no plano gratuito | sem custo; excesso devolve erro 429 | sem custo; 10.000 "Neurons"/dia, depois falha (não cobra no Free) | sem custo; 50 chamadas/dia (1.000 com US$ 10 de crédito) | sem custo |
| Usa seus dados para treinar | a página não afirma | **não** | não registra por padrão; depende do modelo final | **sim** (e há revisão humana) |
| Retenção | não retém por padrão; até 30 dias para abuso; opção de retenção zero | não retém após a resposta | depende do provedor final | retém e usa para melhorar produtos |
| Feito para produção | sim | sim | **não** (o próprio OpenRouter avisa) | não com dado real |
| Conta nova necessária | sim | **não: você já tem conta Cloudflare** (é onde roda o site) | sim | sim (Google) |
| Recomendação | **1ª opção de reserva** | **2ª opção** (mais simples de ativar) | só para testes | **não usar** com dado de cliente |

Região: os quatro processam fora do Brasil (como a Anthropic, que já está em uso). Para dado pessoal, a LGPD exige base para
transferência internacional (cláusulas contratuais/termos do fornecedor). É uma decisão jurídica, não técnica: por isso a recomendação
de começar só com dado público.

## Roteiro do que você precisa fazer

Regra para todos: **conta sem cartão / sem faturamento ativo** (assim não há como gerar cobrança), e **a chave vai direto no Render**,
nunca no chat. Depois de cada um, me avise: eu ligo, testo com dados fictícios e registro o resultado.

### 1. Cloudflare Workers AI (a mais rápida: sem conta nova)

1. Entre em **dash.cloudflare.com** com a conta que já hospeda o site.
2. Menu **AI → Workers AI** → **Use REST API**.
3. Copie o **Account ID** mostrado na página.
4. Clique em **Create a Workers AI API Token**, mantenha só a permissão de Workers AI e crie. Copie o token (aparece uma vez).
5. No Render → **b2bon-api** → Environment, crie:
   - `CLOUDFLARE_AI_ACCOUNT_ID` = o Account ID
   - `CLOUDFLARE_AI_API_TOKEN` = o token
   - `CLOUDFLARE_AI_PLANO` = `gratuito`
   (o modelo e a ativação eu configuro depois do teste.)

### 2. Groq

1. Crie a conta em **console.groq.com** (pode entrar com o Google da CyberFort). Não cadastre cartão.
2. Em **Settings → Data Controls**, ative a opção de **retenção zero** se ela aparecer para a sua conta.
3. Em **API Keys → Create API Key**, dê o nome `b2bon-producao` e copie a chave.
4. No Render → **b2bon-api** → Environment: `GROQ_API_KEY` = a chave e `GROQ_PLANO` = `gratuito`.

### 3. OpenRouter (opcional, só se quiser uma terceira reserva para testes)

1. Conta em **openrouter.ai**, sem créditos.
2. **Settings → Privacy**: desligue a permissão para provedores que registram ou treinam com os dados.
3. **Keys → Create Key**; no Render: `OPENROUTER_API_KEY` e `OPENROUTER_PLANO` = `gratuito`.

### 4. Google Gemini

**Não criar por enquanto.** No plano gratuito o Google usa os textos para melhorar os produtos e pessoas podem lê-los; os próprios
termos pedem para não enviar dado pessoal ou confidencial. Só faria sentido no plano pago, com avaliação.

## O que eu faço depois que as chaves estiverem no Render

1. Escolho o modelo de cada um no catálogo vigente (nenhum é assumido; modelo gratuito pode ser retirado).
2. Teste real **com dados fictícios** no staging; registro o resultado em PROVEDORES_IA.md.
3. **Atenção, limite do código atual:** a reserva hoje é "tudo ou nada": ligada, ela vale para **todas** as tarefas de IA, inclusive as
   com dado de cliente, e por isso só liga com `*_APROVADO_DADOS_REAIS=true` (a sua aprovação de LGPD). Para ligar **só nas tarefas de
   dado público** (editais, normalização de texto), preciso de um ajuste pequeno no código: uma lista de tarefas permitidas por
   provedor. Faço quando você decidir seguir por esse caminho.
4. Teto diário de 200 chamadas por provedor (já existe), para nenhuma reserva ser usada sem limite.

## Decisão e configuração aplicada (05/11/2026)

- O PO escolheu a opção **"Tudo"**: a reserva vale para todas as tarefas, inclusive com dados de clientes, e ele aceitou a
  transferência internacional para Groq e Cloudflare (EUA) do ponto de vista da LGPD. A Anthropic já estava nessa situação.
- Produção (b2bon-api), variáveis definidas:
  - `AI_PROVEDORES_FALLBACK=groq,cloudflare`;
  - `GROQ_MODELO=llama-3.3-70b-versatile` e `GROQ_APROVADO_DADOS_REAIS=true`;
  - `CLOUDFLARE_AI_MODELO=@cf/meta/llama-3.3-70b-instruct-fp8-fast` e `CLOUDFLARE_AI_APROVADO_DADOS_REAIS=true`;
  - as chaves e os planos (`gratuito`) foram salvos pelo PO.
- Conferência: **AI FinOps → IA de reserva → Testar**. O botão envia um texto fictício direto a cada reserva.
- Política de Privacidade atualizada (seção 6). Teste real em 05/11/2026: as duas reservas responderam (Groq 375 ms, Cloudflare 1410 ms).
