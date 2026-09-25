# 11 — OPPORTUNITY INTELLIGENCE (Fase 6, §20–§26)

Contexto: `app/contexts/opportunity/` (contrato: `contract.py`). API:
`/api/v1/inteligencia/oportunidades/*` (gate: módulo CRM). UI: card
**Inteligência da oportunidade** na tela completa do negócio.

```
Reunião (transcrição/resumo) ou nota ──► Need Extraction (IA, via AI Gateway)
                                            │  grounding: citação literal obrigatória
                                            ▼
                         necessidade_oportunidade  [sugerida] ──humano──► confirmada | descartada
                                            │                                  (Learning Loop)
      Offer Intelligence (oferta §25) ──┐   │
      Conta / decisores / atividades ───┼───┴──► motores determinísticos (C0, sem custo de IA)
      MAP (risco de churn, NPS) ────────┘            Discovery Gap · Next Best Offer
                                                     Next Best Action · White Space
                                                     Buying Signals · Riscos · Stakeholders
                                                                 │
                                                                 ▼
                                               OPPORTUNITY INTELLIGENCE CARD
```

## 1. Explicabilidade (GATE)

Todo item recomendável é uma `explicavel.Recomendacao`:
`tipo, titulo, motivo, evidencias[], confianca (ALTA|MEDIA|BAIXA), fonte
(motor e versão, ex.: opportunity.next_best_offer.v1), gerado_em, dados`.
`recomendacao()` recusa construir item sem motivo, sem evidência ou sem
fonte. Cada evidência diz o tipo (necessidade, decisor, conta, oferta,
interação, reunião, MAP, lacuna), a referência, o trecho e a natureza:
`confirmado_por_humano`, `sugestao_ia_nao_confirmada`, `cadastro`,
`calculo_deterministico` ou `ausencia_de_dado`.

Metodologia declarada no card: `RULE_BASED_V1` (regras, não ML).

## 2. Need Extraction / Meeting Intelligence

- Feature de IA `opportunity.extracao_necessidades` (C2, `opportunity_agent`,
  conteúdo externo → bloco delimitado + instrução anti-injeção). Medida no
  ledger e no FinOps como qualquer outra.
- Fonte: reunião escolhida, ou a última reunião da conta com transcrição
  ou resumo, ou uma atividade do negócio (nota, ligação, e-mail, WhatsApp).
- **Grounding**: item sem citação encontrada literalmente no texto é
  descartado antes de gravar (contado em `descartadas_sem_evidencia`).
- Tudo nasce `sugerida`. O vendedor confirma (com ou sem edição) ou
  descarta; isso gera `evento_aprendizado` GERADO/APROVADO/EDITADO/REJEITADO.
  Necessidade digitada pelo vendedor já nasce `confirmada`.
- Categorias: dor, requisito, orçamento, autoridade, prazo, concorrência,
  objeção, outro.

## 3. Discovery Gap (§23)

Dimensões: necessidade, autoridade, orçamento, prazo, concorrência. Cada
uma é CONFIRMADO, SUGERIDO (só sugestão de IA ou papel sugerido pelo
cargo) ou FALTANDO. Autoridade também se confirma por decisor com papel
DECISION_MAKER/ECONOMIC_BUYER confirmado; concorrência, por interação MAP
`mencionou_concorrente`. Se qualquer uma não está confirmada:
`INSUFFICIENT_INFORMATION` + lista do que falta + perguntas (padrão +
`perguntas_descoberta` da oferta do negócio).

## 4. Next Best Offer (§21)

Por oferta com `disponivel_para_venda` que a conta ainda não comprou:

| Sinal | Pontos |
|---|---|
| Necessidade confirmada casa com problemas resolvidos/dores/casos de uso/requisitos | 25 cada (teto 60 com as sugeridas) |
| Necessidade só sugerida pela IA | 10 cada |
| Segmento da conta ∈ indústrias da oferta | 15 |
| Cargo de decisor ∈ personas | 10 |
| Mesmo ICP | 15 |
| Incompatibilidade atingida | −30 e risco declarado |

Confiança ALTA exige necessidade confirmada + sinal de perfil. Casamento
de texto determinístico (tokens sem acento e sem stopwords, radical de 6
letras, ao menos metade dos termos do menor texto em comum), mostrado na
evidência. Saída: oferta, `fit_score`, motivo, evidências, confiança,
riscos, cross-sell, upsell, pré-requisitos, objeções conhecidas.
Sem ofertas, sem necessidades ou sem Offer Intelligence →
`INSUFFICIENT_INFORMATION` com a lista. Declara o que **não** cruza ainda:
Corporate Brain (sem busca semântica, D-017) e Business Graph (Fase 7).

## 5. Next Best Action (§22)

Regras em ordem: priorizar remediação (cliente com churn crítico) →
envolver decisor → discovery adicional → validar orçamento → **não
enviar proposta ainda** (lacunas com probabilidade ≥ 60%) → retomar
contato (> 14 dias sem atividade) → definir próximo passo → validar
pré-requisitos (assessment) → demonstração → preparar proposta (discovery
completo + decisor confirmado + sem churn crítico). Negócio ganho/perdido
não recebe ação de venda. Nada é executado sozinho.

## 6. White Space (§24) e MAP (§26)

Por conta: produtos atuais (ofertas de negócios ganhos), potenciais (fit >
0), cross-sell/upsell cadastrados nas ofertas atuais, necessidades
confirmadas sem oferta que as atenda, valor já ganho. **Valor potencial
só quando todas as ofertas potenciais têm ticket médio**; senão `null` com
o motivo. MAP: churn crítico suprime cross-sell/upsell em NBO e White
Space e vira "Priorizar remediação"; cliente saudável + NPS promotor +
espaço em branco vira "Oportunidade de expansão".

## 7. Offer Intelligence (§25)

Colunas novas em `oferta` (todas opcionais): categoria, problemas
resolvidos, dores, casos de uso, personas, indústrias, requisitos,
pré-requisitos, incompatibilidades, objeções, cases, cross-sell, upsell,
bundles (listas), modelo de precificação, ticket médio, margem média,
playbook, perguntas de descoberta, critérios de qualificação,
`disponivel_para_venda` (D-021). ICP e diferenciais/provas já existiam.
Edição parcial: o PUT só altera esses campos quando vêm no corpo. Ticket
e margem são dados do tenant sobre a própria oferta, não preço da B2B ON.

## 8. Endpoints

| Método | Path | O que faz |
|---|---|---|
| GET | `/inteligencia/oportunidades/{negocio}/card` | Card completo (determinístico, sem IA) |
| GET | `/inteligencia/oportunidades/{negocio}/necessidades` | Lista (`incluir_descartadas`) |
| POST | `/inteligencia/oportunidades/{negocio}/necessidades` | Registro manual (confirmada) |
| POST | `/inteligencia/oportunidades/{negocio}/necessidades/extrair` | IA; `reuniao_id` ou `atividade_id` opcionais; rate limit de IA |
| PATCH | `/inteligencia/oportunidades/necessidades/{id}` | Confirmar/editar/descartar |
| GET | `/inteligencia/oportunidades/contas/{conta}/white-space` | White Space da conta |

## 9. Limites conhecidos

- Casamento lexical: sinônimos sem termo em comum não casam (TD-051).
- Pesos das regras são padrão técnico, sem calibração com resultado real
  (TD-052; Learning Loop já grava as decisões para calibrar).
- Business Graph e Corporate Brain fora do NBO até as Fases 7 e 17.
