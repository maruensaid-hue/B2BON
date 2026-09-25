# OPEN ISSUES

Questões que exigem decisão do Product Owner ou correção fora do escopo
da fase corrente. Status: `OPEN | DECIDED | RESOLVED`.

| ID | Severidade | Questão | Evidência | Quem decide | Status |
|---|---|---|---|---|---|
| OI-001 | **Crítica (produção)** | Planos "PREDATOR Starter/Professional/Enterprise" têm franquia, cadências, campanhas e enriquecimento = 0. Quem paga PREDATOR avulso não consegue usar o produto. Fase 0 proíbe alterar planos. **Precisa de hotfix autorizado** (migração corrigindo os limites; valores a definir pelo PO, por exemplo iguais aos da suíte na mesma faixa). | `PRICING_CURRENT_STATE.md` §4 | PO | OPEN |
| OI-002 | Alta | Rotas no módulo errado (C1, C3–C7): MAP-only recebe 403 no painel; PREDATOR-only não gera lista; CRM-only não cria conta pelo Kanban. Correção planejada na Fase 1. Se houver clientes avulsos ativos, pode justificar hotfix antes. | `DOMAIN_DEPENDENCY_MAP.md` §4 | PO (prioridade) | OPEN |
| OI-003 | Média | Preço duplicado entre DB, `Planos.tsx` e `bootstrap_tenant.py`. Planejado para a Fase 14. | `PRICING_CURRENT_STATE.md` §1 | — | OPEN |
| OI-004 | Média | Quais dados, em Conta/Decisor, são "de quem"? Na Fase 1, Organization/Person viram shared kernel. É preciso confirmar se um tenant só-PREDATOR deve **ver** contas no CRM (hoje não vê: gate CRM). | `DOMAIN_DEPENDENCY_MAP.md` §3 | PO | OPEN |
| OI-005 | Média | CI não roda em `staging` (o branch de desenvolvimento). Incluir `staging` em `on.push/pull_request` do `ci.yml`? | `SECURITY_BOUNDARIES.md` S5 | PO / DevOps | OPEN |
| OI-006 | Baixa | "MAP" tem dois produtos com o mesmo nome: saúde de contas (vendido) e motor de churn de tenants (interno CyberFort). O alvo §7 trata só do primeiro? O motor interno fica fora dos contratos públicos? | `MAP_CURRENT_STATE.md` §1 | PO | OPEN |
| OI-007 | Baixa | "Churn prediction" hoje é um score por regras. A página de vendas não promete ML, mas o alvo §7 fala em "análise preditiva". Manter a linguagem honesta até existir modelo. | `MAP_CURRENT_STATE.md` §2 | PO | OPEN |
| OI-008 | Info | Nome do módulo de rede: o código e a UI usam "Shoal" (ex-"Rede Social"). O Master Prompt usa "Business Network". Assumido: Business Network = Shoal (D-004). | — | PO (confirmar) | OPEN |
| OI-009 | Info | Valores reais em produção da tabela `plano` não foram lidos (auditoria só do código). Conferir antes de qualquer fase comercial. | — | PO / Ops | OPEN |
