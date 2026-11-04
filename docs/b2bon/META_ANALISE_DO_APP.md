# Análise do app pela Meta: roteiro dos vídeos e textos das permissões

App: **B2B ON Mensageria** (ID 1068205709075421), portfólio **B2BON** (verificado).
Objetivo: passar o app de "Em desenvolvimento" para **publicado**, com acesso avançado às permissões do WhatsApp, para que os números
dos clientes possam enviar mensagens pela plataforma.

> A análise é feita por pessoas da Meta, em geral em inglês. Por isso os textos para colar no formulário estão em inglês; a explicação
> de cada passo está em português. Os vídeos podem ter a tela em português, mas precisam de **legenda ou narração em inglês**
> (ou texto na tela) explicando o que está acontecendo.

---

## 1. Antes de enviar: o que conferir no painel do app

Em developers.facebook.com → B2B ON Mensageria:

| Onde | O que precisa estar preenchido | Valor |
|---|---|---|
| Configurações do app → Básico | URL da Política de Privacidade | `https://b2bon.cyberfort.com.br/privacidade` |
| Configurações do app → Básico | URL dos Termos de Serviço | `https://b2bon.cyberfort.com.br/termos` |
| Configurações do app → Básico | Exclusão de dados do usuário | escolher **"URL de instruções de exclusão de dados"** e usar `https://b2bon.cyberfort.com.br/privacidade` (a seção 4, "Direitos do titular", explica como pedir a eliminação) |
| Configurações do app → Básico | Ícone do app (1024 × 1024) | logo do B2B ON |
| Configurações do app → Básico | Categoria | **Negócios e páginas** |
| Configurações do app → Básico | E-mail de contato | e-mail da CyberFort que você acompanha |
| Configurações do app → Básico | Domínios do app | `cyberfort.com.br` e `b2bon.cyberfort.com.br` |
| WhatsApp → Configuração | URL de callback do webhook | `https://b2bon-api.onrender.com/api/v1/webhooks/whatsapp/meta` (já deve estar; é a que recebe as respostas dos clientes) |
| Análise do app → Verificação | Verificação da empresa | **concluída** (portfólio B2BON verificado em 04/11/2026) |

Também é exigido um **usuário de teste** para a Meta entrar na plataforma. Crie no B2B ON uma conta só para isso (não use a sua), com
papel **admin** num tenant de demonstração que já tenha o número conectado, e informe login e senha no campo de instruções da análise.
Troque a senha depois que a análise terminar.

---

## 2. Permissões a pedir

Em **Análise do app → Permissões e recursos**, pedir **Acesso avançado** para:

1. `whatsapp_business_messaging`
2. `whatsapp_business_management`

(`business_management` só será necessária quando o botão "Conectar com a Meta" estiver funcionando para os clientes; **não peça agora**:
permissão pedida sem uso demonstrável é motivo comum de recusa.)

---

## 3. Vídeo 1 — `whatsapp_business_messaging` (enviar e receber mensagens)

**Duração alvo:** 2 a 3 minutos. Gravar a tela inteira (navegador + celular espelhado ou filmado ao lado). Evite cortes; a única pausa
aceitável é a espera do ciclo de envio, avisada na legenda.

Roteiro (o que fazer, na ordem):

1. Abra `https://b2bon.cyberfort.com.br` e faça login com o usuário de teste. *(legenda: "Logging in to B2B ON as a business user")*
2. Vá em **Configuração → WhatsApp Business** e mostre o número conectado e o selo **CONECTADO**.
   *(legenda: "The business connected its own WhatsApp Business number")*
3. Vá em **PREDATOR → Cadências**, abra uma cadência com toque de WhatsApp e mostre o **template aprovado** selecionado.
   *(legenda: "Outreach messages use templates approved by Meta")*
4. Abra **Aprovações**, mostre a mensagem para um contato de teste (o seu celular) e clique em **Aprovar**.
   *(legenda: "A person reviews and approves each message before it is sent")*
5. A mensagem aprovada sai no próximo ciclo de envio (alguns minutos). Pode pausar a gravação enquanto espera, desde que a legenda diga
   isso. Mostre o celular recebendo a mensagem no WhatsApp.
   *(legenda: "Approved messages are sent in the next sending cycle (a few minutes). The contact receives it on WhatsApp")*
6. No celular, **responda** a mensagem.
7. Volte ao B2B ON, abra a conta do contato e mostre a resposta registrada na conversa.
   *(legenda: "Replies arrive through the webhook and are shown to the business")*
8. Mostre que, ao responder "SAIR" (ou "não tenho interesse"), o contato entra em opt-out e não recebe mais mensagens.
   *(legenda: "Opt-out is respected automatically")*

**Texto para colar (como o app usa a permissão):**

> B2B ON is a B2B sales platform. Each business customer connects its own WhatsApp Business number and uses it to contact other
> companies' decision makers who are part of its prospecting lists. We use whatsapp_business_messaging to (1) send messages from the
> customer's own number, always with a Meta-approved template for the first contact and only after a person on the customer's team
> reviews and approves the message, and (2) receive the replies through our webhook so the customer can continue the conversation
> inside the platform. Contacts can opt out at any time and are automatically blocked from future messages. We never send messages from
> a number the customer has not connected, and we do not send promotional content outside approved templates.

---

## 4. Vídeo 2 — `whatsapp_business_management` (gerenciar a conta e os templates)

**Duração alvo:** 1 a 2 minutos.

1. Login com o usuário de teste. *(legenda: "Logging in as the business administrator")*
2. **Configuração → WhatsApp Business**: clique em **Testar conexão** e mostre o número, o nome verificado e a qualidade lidos da Meta.
   *(legenda: "We read the phone number, verified name and quality rating from the WhatsApp Business Account")*
3. **PREDATOR → Cadências → toque de WhatsApp**: abra a lista de templates e mostre que ela vem da conta do cliente, com o status
   de aprovação. *(legenda: "We list the message templates of the customer's WhatsApp Business Account and their approval status")*
4. Mostre o aviso que aparece quando não há template aprovado (o envio fica bloqueado até haver um).
   *(legenda: "Without an approved template, the first message is not sent")*

**Texto para colar:**

> We use whatsapp_business_management to read the customer's own WhatsApp Business Account: the phone number details (display number,
> verified name and quality rating) so the customer can confirm the connection, and the list of message templates with their approval
> status so the customer can choose an approved template for each outreach step. We only access the WhatsApp Business Account that the
> customer itself connected to B2B ON, and only to show this information and to send messages on its behalf.

---

## 5. Instruções para o revisor (campo "notas de teste")

> Test user: [e-mail do usuário de teste] / [senha]. After logging in at https://b2bon.cyberfort.com.br, go to Configuração (Settings)
> → WhatsApp Business to see the connected number and click "Testar conexão" (Test connection). Outreach messages are in PREDATOR →
> Cadências (Sequences); pending messages are approved in Aprovações (Approvals) before being sent, and go out in the next sending
> cycle (a few minutes). The interface is in Portuguese; the
> videos include English captions for every step.

---

## 6. Depois da aprovação

1. Em **Configurações do app → Básico**, mude o **Modo do app** para **Ao vivo** (Publicado).
2. Me avise: eu confiro nos logs o primeiro envio real para um número de cliente.
3. Se a Meta recusar, cole aqui o motivo exato que ela escreveu; a resposta costuma apontar um passo específico do vídeo.
