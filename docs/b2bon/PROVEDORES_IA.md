# Provedores de IA — arquitetura, estado e como habilitar

Verificado nas documentações oficiais em **2026-10-20**. Limites e termos mudam: revalidar antes de habilitar.

## Arquitetura

- Porta única: `LLMProvider.generate(LLMRequest) -> LLMResponse` (`app/llm/base.py`). O **AI Gateway** (`app/contexts/intelligence/gateway.py`)
  é o único caminho de código para chamar um LLM e já aplica orçamento, AI Credits, ledger, cache, cost guard e disjuntor.
- `ClaudeProvider` (Anthropic) continua sendo o padrão e **não foi alterado**. Os adapters novos ficam em `app/llm/provedores.py`.
- `app/llm/fallback.py` registra os quatro provedores, avalia se cada um pode receber chamadas (`status_provedores`) e monta o
  `ProvedorComFallback` quando — e só quando — há provedores ativos. **Sem configuração, `get_llm_provider` devolve o `ClaudeProvider`
  puro**, idêntico ao comportamento anterior.
- Só falha **do provedor** (rede, timeout, 429, 5xx, 400/401/403/404, corpo ilegível) aciona o próximo da lista. Resposta vazia ou cortada
  por limite de tokens é falha de conteúdo e não troca de fornecedor. Cada provedor tem disjuntor próprio e a chamada que usa fallback
  fica no ledger de uso (`registro_uso_ia.provider`) com o provedor real.
- O `model` do request é um id da Anthropic: **nunca** é enviado a outro fornecedor; cada adapter usa o modelo configurado para ele.

## Estado de cada provedor

| Provedor | Adapter implementado | Teste simulado aprovado | Teste real aprovado | Habilitado por padrão | Aprovado p/ dados reais |
|---|---|---|---|---|---|
| Anthropic (Claude) | sim | sim | **sim — em produção** | sim | sim |
| Cloudflare Workers AI | sim | sim | **não realizado** | não | **não** |
| GroqCloud | sim | sim | **não realizado** | não | **não** |
| OpenRouter | sim | sim | **não realizado** | não | **não** |
| Google Gemini | sim | sim | **não realizado** | não | **não** |

“Teste simulado” = `tests/unit/test_provedores_ia.py` com `httpx.MockTransport` (contrato de URL, cabeçalhos, corpo, resposta, erros, timeout,
fallback). **Nenhum dos quatro foi chamado de verdade** (não há credenciais). Dois pontos do contrato ficam sem confirmação real:
o corpo `messages` e o campo `usage` do Workers AI (a documentação de início rápido mostra só `prompt`).

## Regras que impedem chamada silenciosa e cobrança inesperada

Um provedor só recebe tráfego se **todas** as condições valerem; caso contrário nem o adapter é construído e `GET /api/v1/admin/provedores-ia`
(super_admin) mostra o motivo:

1. está em `AI_PROVEDORES_FALLBACK` (ordem de tentativa, separada por vírgula; padrão vazio);
2. tem credencial **e** modelo configurados (nenhum modelo é assumido: modelo gratuito pode ser retirado a qualquer momento);
3. `<PROVEDOR>_APROVADO_DADOS_REAIS=true` — só depois da avaliação de privacidade (o fallback recebe o mesmo prompt, com dados do cliente);
4. plano `gratuito`, ou `AI_FALLBACK_PERMITE_PAGO=true` com autorização de custo (`<PROVEDOR>_PLANO` aceita só `gratuito` ou `pago`);
5. OpenRouter gratuito: o id do modelo **termina em `:free`**;
6. teto diário `AI_FALLBACK_LIMITE_DIARIO` (padrão 200 chamadas bem-sucedidas por provedor/dia, contadas no ledger); acima disso o provedor é pulado.

O plano `gratuito` é uma **declaração do operador**: não há como a plataforma verificá-lo. Use chaves de projeto/conta **sem faturamento ativo**.

## Como habilitar cada provedor (quando houver credencial e aprovação)

Passos comuns: (a) revisar a política de dados abaixo e registrar a aprovação; (b) criar a credencial com o menor escopo e sem faturamento
(plano gratuito); (c) definir as variáveis no Render (nunca no código); (d) conferir `GET /api/v1/admin/provedores-ia` (estado `ativo`);
(e) fazer um teste real com **dados fictícios** antes de marcar `teste_real` como aprovado neste documento.

| Provedor | Variáveis | Limites documentados | Dados e retenção documentados |
|---|---|---|---|
| Cloudflare Workers AI | `CLOUDFLARE_AI_ACCOUNT_ID`, `CLOUDFLARE_AI_API_TOKEN`, `CLOUDFLARE_AI_MODELO` (id do catálogo, ex.: `@cf/meta/...`), `CLOUDFLARE_AI_PLANO`, `CLOUDFLARE_AI_APROVADO_DADOS_REAIS` | Free: 10.000 Neurons/dia; acima, as chamadas falham (sem cobrança no Free). Paid: US$ 0,011 / 1.000 Neurons além da franquia | Não treina com o conteúdo; não retém após a inferência padrão; recursos com estado (AI Gateway com log/cache, R2, KV) seguem a retenção própria; metadados são retidos |
| GroqCloud | `GROQ_API_KEY`, `GROQ_MODELO`, `GROQ_PLANO`, `GROQ_APROVADO_DADOS_REAIS` | Por modelo/plano (ex. Developer: 30 RPM, 1K RPD no `gpt-oss-120b`); excesso = 429; não está documentado se exceder o gratuito cobra | Não retém por padrão; pode registrar até 30 dias para depuração/abuso; ZDR disponível nos Data Controls; a página não afirma nada sobre treinamento |
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_MODELO` (com `:free` no plano gratuito), `OPENROUTER_PLANO`, `OPENROUTER_APROVADO_DADOS_REAIS` | `:free`: 50 req/dia sem créditos; 1.000/dia com ≥ 10 créditos. “Não servem para produção”; sem garantia de disponibilidade | Não registra prompts por padrão; não roteia a provedores que registram, salvo configuração de privacidade; **não está claro se vale igual para modelos gratuitos** — validar na conta |
| Google Gemini | `GEMINI_API_KEY`, `GEMINI_MODELO`, `GEMINI_PLANO`, `GEMINI_APROVADO_DADOS_REAIS` | Por projeto, não garantidos, sujeitos a mudança; não está documentado se exceder o gratuito cobra | **Gratuito: Google usa prompts/respostas para melhorar produtos, revisores humanos podem lê-los e os termos pedem para não enviar dados pessoais/confidenciais.** Pago: não usa para melhorar produtos; registra por tempo limitado. No EEE/Suíça/Reino Unido valem os termos pagos |

**Recomendação de privacidade:** o Gemini no nível gratuito **não deve** ser aprovado para dados reais de clientes (prompts do B2B ON carregam
contatos e contexto comercial). Os demais dependem de avaliação jurídica/LGPD (transferência internacional, operador, DPA) fora do escopo do código.

## Pendências para ativação real

- Credenciais de cada provedor (responsável: PO) e decisão de custo se algum plano pago for desejado.
- Avaliação de privacidade/LGPD e marcação de `*_APROVADO_DADOS_REAIS`.
- Teste real com dados fictícios e registro do resultado neste documento.
- Hoje, com a Anthropic fora do ar e **nenhum** fallback aprovado, o comportamento segue o já existente: erro claro, disjuntor, coleta preservada.
