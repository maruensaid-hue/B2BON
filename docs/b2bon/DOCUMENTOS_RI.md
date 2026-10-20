# Documentos de Relações com Investidores (RI) → indicadores rastreáveis (V5.2.1, Fase 5)

Sem IA em nenhum ponto da extração e da persistência. O texto do PDF é **dado não confiável**: vai só para regras (regex), nunca para um modelo e nunca é executado.

## Fluxo

`POST /contas/{id}/ri/documentos` (arquivo) ou `/ri/documentos/url` (URL pública informada por quem usa) → leitura segura do PDF → indicadores e sinais → `GET /contas/{id}/ri/financeiro` (visão única: site + RI, **lado a lado, nunca fundidos**). Também: listar, detalhar, reprocessar (só origem URL), excluir e **conferir manualmente** cada indicador (`conferido_manualmente`/`rejeitado`). O arquivo **não é guardado**: só hash, metadados e evidências (evita custo de armazenamento no Neon e exposição desnecessária).

## Segurança do processamento

| Risco | Controle |
|---|---|
| Arquivo que finge ser PDF (extensão/`Content-Type` mentem) | só aceita se o conteúdo tem `%PDF-` nos primeiros 1024 bytes **e** o leitor consegue abri-lo |
| PDF malformado / bomba de descompressão / milhares de páginas | leitura em **subprocesso** com timeout (25 s, o processo é morto), limite de memória (`RLIMIT_AS`, só POSIX; no Windows de dev vale o timeout), máximo de 300 páginas, 120 mil caracteres por página e 2,5 milhões no total |
| PDF protegido por senha | só lê se abrir com senha vazia; senão recusa |
| Conteúdo ativo (`/JavaScript`, `/Launch`, `/EmbeddedFile`) | **nada é executado** (o leitor só extrai texto); gera aviso no documento |
| SSRF na URL | `requisitar_publico`: só http(s), portas 80/443, IP público resolvido e fixado, no máximo 3 redirecionamentos, 25 MB; a resposta precisa ser PDF |
| Prompt injection | o texto nunca vai a um modelo na extração; no briefing/estratégia entra como dado em bloco isolado (`bloco_dados_externos`) com a instrução de não transformar fato em necessidade |
| Vazamento entre tenants | todas as consultas filtram o tenant; acesso pelo mesmo escopo de conta do CRM; coberto pela varredura de isolamento |
| Abuso/custo | limite por tenant (12 leituras em 5 min) |
| OCR | **não existe** (nenhum serviço pago novo): PDF digitalizado devolve "sem texto" |

## O que é extraído e como se preserva a proveniência

Receita líquida/bruta, EBITDA, lucro líquido, **prejuízo líquido** (indicador próprio, em módulo; nunca vira lucro negativo), dívida líquida/bruta, caixa e equivalentes, capex; margem líquida **derivada** (só do mesmo documento, período e moeda). Cada indicador guarda valor, moeda, escala, **valor como escrito**, período, **página**, trecho, método (`regex_ri_v1`), confiança, estado de validação, fórmula/origens (derivados), data da coleta e, via documento, nome, URL e data de publicação **informada por quem enviou** (nunca inferida do PDF). Sinais qualitativos (aquisição, expansão, investimento, reorganização) ficam como sentença literal com a página, sem interpretação.

## O que NÃO é feito (de propósito)

- Só vira indicador número escrito **com moeda ao lado do nome**. Tabela de colunas sem "R$" **não** é lida: é preferível deixar de extrair a atribuir o valor de outra coluna.
- Moeda e escala **nunca são convertidas**; BRL e USD convivem.
- Período ambíguo (mais de um no trecho, ex.: "3T25, alta sobre o 3T24") reduz a confiança e avisa; período ausente é `None`.
- Dois documentos com valores diferentes para o mesmo indicador/período/moeda marcam **ambos** `conflitante`; nenhum vence sozinho. A conferência manual resolve.
- "Caixa" solto (fluxo ≠ saldo) e "investimentos" solto (financeiros ≠ capex) ficam de fora.
- Um indicador **não** autoriza afirmar que a empresa precisa de um produto; o texto enviado à IA diz isso explicitamente.

## Limitações conhecidas

PDFs só-imagem, tabelas sem moeda, balanços com valores em colunas e notas explicativas não são lidos. A busca automática do PDF no site de RI da empresa **não foi implementada** (o usuário informa o arquivo ou a URL). O painel visual na tela da conta **não foi feito**: a API (`/ri/financeiro`) e o contexto dos prompts de briefing e estratégia estão prontos.
