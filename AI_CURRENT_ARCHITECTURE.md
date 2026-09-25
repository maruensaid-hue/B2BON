> **Histórico (2026-09-17).** A referência atual de arquitetura está em
> [`docs/b2bon/`](docs/b2bon/00_MASTER_ARCHITECTURE.md) (Master Prompt v4, D-003).
> Este arquivo tem trechos desatualizados; em caso de divergência, vale `docs/b2bon/`.

# AI_CURRENT_ARCHITECTURE.md — B2B ON (auditoria factual, 2026-09-17)

O que existe hoje na camada de IA. Sem aspiração — cada afirmação abaixo
foi confirmada lendo o código, não deduzida.

## 1. Provider abstraction

```python
# app/llm/base.py
class LLMIndisponivel(Exception): ...

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse: ...

# app/llm/schemas.py
class LLMRequest(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 1.0

class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
```

Uma única implementação real: `app/llm/claude_provider.py::ClaudeProvider`
(SDK oficial da Anthropic, `settings.anthropic_model`, timeout 25s).
Já existe abstração de provider (item 7 do master prompt) — só falta
mais de um provider concreto pra ela valer algo na prática hoje.

`generate()` já trata, por incidente real documentado no próprio
código: chave ausente, erro da API, `TypeError` de SDK (drift de
assinatura), resposta sem bloco de texto (`ThinkingBlock`), texto vazio,
e `stop_reason == "max_tokens"` (resposta cortada) — todos convertidos
em `LLMIndisponivel`, nunca um crash não tratado.

Injeção: `app/api/deps.py::get_llm_provider()` sempre devolve
`ClaudeProvider()`, sem branch condicional (diferente da maioria dos
outros providers no mesmo arquivo, que alternam por config). Todo call
site passa por `app/services/llm_helpers.py::gerar(llm, request)`, que
converte `LLMIndisponivel` em `RegraNegocioViolada` com mensagem em
português — nenhuma falha de LLM chega numa rota como 500 genérico.

## 2. Todos os pontos de uso de IA hoje (8, nenhum além destes)

| Feature | Onde | Passa pela fila de Aprovação? |
|---|---|---|
| Rascunho de mensagem de cadência | `cadencia_service.py::gerar_para_lote`/`_gerar_conteudo_toque` | **Sim** |
| Mensagem de pedido de indicação | `indicacao_service.py::solicitar` | **Sim** |
| Resumo do site institucional (enriquecimento) | `conta_service.py::enriquecer` | Não — grava em `CampoEnriquecido`, nunca é enviado a ninguém |
| Amostra de tom de comunicação (preview de config) | `comunicacao_service.py::gerar_amostra` | Não — só preview, nunca sai |
| Assistente de FAQ (chat interno de ajuda) | `faq_service.py::responder` | Não — responde ao próprio usuário logado |
| Resumo de transcrição de reunião → nota de CRM | `meeting_bot_service.py::processar_transcricao` | Não — vira `Atividade`, não é enviado |
| Roteiro de resgate de conta em risco (nível tenant, uso do time CyberFort) | `motor_service.py::gerar_script_resgate` | Não — texto pra humano copiar manualmente |
| Roteiro de resgate de conta em risco (nível vendedor) | `saude_conta_service.py::gerar_script_resgate` | Não — mesmo padrão |
| Qualificação conversacional S.H.A.R.K. (auto-resposta a WhatsApp/e-mail entrante) | `qualificacao_service.py::processar_mensagem_recebida` | **N/A — nem chega a ser enviada ao lead** (ver nota) |

**Nota importante sobre o bot de qualificação**: o LLM é instruído a
prefixar a resposta com `CONTINUAR:`, `FAQ:` ou `TRANSFERIR:`. No caso
`CONTINUAR:`, o texto gerado só é gravado num `TurnoConversa`
(`direcao="saida"`) — não existe nenhuma chamada que de fato despache
esse texto pro lead via WhatsApp/e-mail. O único envio real de
WhatsApp nesse fluxo é `notificacao_service.notificar_vendedor`, que
avisa o **vendedor**, não o prospect. Ou seja: hoje esse "agente" é, na
prática, um gerador de roteiro sugerido pra um humano — o mesmo padrão
dos dois "scripts de resgate" — não um agente autônomo enviando
mensagem de verdade.

**Nenhum outro agente/orquestrador existe.** Não há `AgentRegistry`,
não há `AIOrchestrator`, não há múltiplos agentes especializados (ICP
Agent, Intent Agent, Stakeholder Agent, etc.) — cada feature acima é
uma chamada única, direta, síncrona a `llm_helpers.gerar()`, sem estado
entre chamadas, sem ferramentas (tool calling), sem decisão de "qual
agente/modelo usar".

## 3. Human-in-the-loop — já implementado, robusto

Exatamente o que a seção 4 do master prompt pede já existe:

```
Mensagem.status: rascunho | aguardando_aprovacao | aprovado | enviado | falhou | cancelado
Aprovacao.status: pendente | aprovado | editado | rejeitado
```

Máquina de estados (`app/services/aprovacao_service.py`):
`criar_proposta` → `aguardando_aprovacao`/`pendente` (ou auto-aprovado
na hora se existir `RegraAutoAprovacao` casando o template, recurso
exclusivo do plano Enterprise) → `aprovar`/`aprovar_lote` →
`aprovado` (grava `aprovador_id` + `decidido_em`) → só então
`envio_service.processar_pendentes` (linha ~107) considera a mensagem
candidata a envio real:

```python
Mensagem.status.in_(["aprovado", "falhou"]),
Mensagem.tentativas_envio < MAX_TENTATIVAS_ENVIO,
Mensagem.agendado_para.isnot(None),
Mensagem.agendado_para <= agora,
```

Uma mensagem em `aguardando_aprovacao` é estruturalmente invisível pro
disparador — não é uma checagem "a mais", é o próprio filtro da query
que decide o que sai. LinkedIn nunca é autoenviado mesmo aprovado —
vira uma `TarefaLinkedin` pra um humano executar manualmente (decisão
deliberada, risco de banimento de conta).

Rastreamento: cada transição chama `auditoria_service.registrar(...)`
(`mensagem_proposta`, `aprovacao_automatica_por_regra`,
`aprovacao_aprovada`, `aprovacao_rejeitada`, `mensagem_editada` —
grava conteúdo antes/depois —, `mensagem_enviada`, etc.), com
`ator_id` e timestamp; `Aprovacao.aprovador_id`/`decidido_em` também
ficam na própria linha.

**O que falta versus o master prompt**: os campos extras pedidos
(`generated_by`, `generated_at`, `edited_by`, `edited_at`, `sent_by`,
`campaign_id` explícito na mensagem) não existem como colunas
dedicadas — a informação equivalente está espalhada entre
`Mensagem`/`Aprovacao`/`AuditLog`, recuperável mas não num único
registro estruturado "ciclo de vida da mensagem".

## 4. Memória, RAG, embeddings — nada disso existe

Grep integral em `app/` por `pgvector`, `embedding`, `vector`, `rag`:
zero ocorrência real (só falsos positivos — vetor de inicialização de
criptografia, nomes de variável não relacionados). Toda chamada de IA
no sistema é um `generate()` único, sem histórico de conversa
persistido entre chamadas (`faq_service.responder` documenta isso
explicitamente: "sem histórico persistido"), sem contexto recuperado
de um banco vetorial, sem memória de longo prazo por tenant/usuário.

Não existe `CompanyIntelligenceProfile`, `UserSalesIntelligenceProfile`,
`LearningEvent`, `Corporate Brain` — nenhum desses conceitos do master
prompt tem qualquer código correspondente hoje. O aprendizado com
edições humanas (seção 11 do master prompt) também não existe: uma
edição de mensagem é auditada (`mensagem_editada` grava conteúdo antes/
depois), mas nada lê esse histórico de volta para ajustar prompts
futuros — é um log, não um loop de aprendizado.

## 5. Context engineering — parcial, implícito, não generalizado

Não existe um "Context Engine" formal, mas o padrão de montar o prompt
a partir de dados já autorizados/escopados por tenant é seguido em
todo call site (cada função de serviço já recebe `tenant_id` e só
busca dados desse tenant antes de montar o prompt — é o mesmo
mecanismo de isolamento usado no resto do sistema, não algo dedicado a
IA). Não há uma camada que decida dinamicamente "quais fontes
recuperar" — cada feature hardcoda quais campos entram no prompt (ex.:
`enriquecer()` concatena HTML/texto do site direto no fim da
instrução).

## 6. Provenance e "não inventar fatos" — parcial, por convenção

Não existe um campo de metadata `source`/`confidence`/
`verification_status` genérico anexado a cada fato usado num prompt.
O que existe, pontualmente:

- `Decisor.origem` e `Conta.origem` guardam de onde veio o dado
  (`receita_federal_cnpj_qsa`, `enriquecimento_contatos`, `manual`,
  `evento`, `lead`, `crm_import`, `rede_social_convite`) — dá pra saber
  a proveniência de uma linha, mas isso não é propagado pro prompt/
  resposta da IA como metadado explícito.
- `CampoEnriquecido.fonte` (`brasilapi_cnpj`, resultado do enriquecimento
  de site, etc.) — mesmo padrão, por campo, não por fato dentro de um
  prompt.
- A instrução de prompt em `conta_service.enriquecer` pede
  explicitamente pra IA só usar o que está no texto fornecido, "nunca
  inventar" — é uma instrução de prompt, não um controle estrutural.

## 7. Defesa contra prompt injection — nenhum framework, mitigação pontual

Não há convenção de delimitador, sandboxing, ou qualquer menção a
"prompt injection" no código. O que atenua o risco hoje, caso a caso:

- `qualificacao_service`: contrato de saída rígido (3 prefixos fixos) +
  fail-safe explícito ("sem prefixo reconhecido, o padrão é
  transferir" pra um humano) — a IA nunca pode, por engano ou
  manipulação, pular direto pra uma ação sem passar por esse filtro de
  prefixo. `_responder_faq` nunca usa texto gerado pela IA como
  resposta final — só o texto pré-curado em `FaqItem.resposta`,
  justamente pra IA não poder ser induzida a responder algo fora do
  script.
- `conta_service.enriquecer` (o único ponto que injeta conteúdo de uma
  fonte externa não controlada — HTML de site institucional de
  terceiro — direto no prompt) não tem nenhuma defesa estrutural além
  da instrução de "não inventar". **Este é o ponto de maior exposição
  real a prompt injection indireto hoje** (uma página maliciosa
  poderia tentar instruir a IA via texto da própria página) — não há
  isolamento explícito entre "dado recuperado" e "instrução".

---
Ver `NETWORK_GAP_ANALYSIS.md` para o que precisaria ser construído pra
chegar no "AI Orchestrator + Corporate Brain + Agent Registry" do
master prompt, e `SECURITY_BOUNDARIES.md` para o item de prompt
injection como risco de segurança formal.
