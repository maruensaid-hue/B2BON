# SECURITY BOUNDARIES — Fase 0 (2026-09-25)

Revisa e corrige o `SECURITY_BOUNDARIES.md` de raiz (2026-09-17). As
seções marcadas **[novo]** ou **[corrigido]** são desta auditoria. O
restante foi reconfirmado no código.

## 1. Fronteiras de confiança

```
 Internet ──► Cloudflare (SPA estático)
    │
    ├─► /api/v1 (JWT)            usuário autenticado; papel + tenant relidos do DB a cada request
    ├─► /api/v1/parceiros        chave de API (SHA-256) — Distribuidores
    ├─► /api/v1/webhooks/*       assinatura por provedor (Meta, SendGrid ECDSA, Mercado Pago HMAC, Recall HMAC)
    ├─► /api/v1/cron/*           X-Cron-Secret (GitHub Actions)
    ├─► /api/v1/optout, /planos, /auth/*, /convites   públicos por desenho
    │
 Backend ──► Anthropic │ BrasilAPI │ sites de terceiros (HTML) │ Brave │ Lusha │ SendGrid/SMTP │ Meta │ Recall │ Google │ Mercado Pago │ Neo4j │ Neon
```

## 2. Isolamento entre tenants

- **Mecanismo**: filtro por `tenant_id` em cada query de serviço. **Sem
  RLS** e sem enforcement estrutural. Um endpoint novo que esqueça o
  filtro vaza dados, e só revisão de código pega isso.
- **[corrigido]** 12 de 92 tabelas não têm coluna `tenant_id*`, não só o
  staging de CNPJ. São 8 globais por natureza e 4 que herdam escopo via
  FK (`campo_enriquecido`, `canal_sala`, `midia_post`,
  `redefinicao_senha`). Nas 4 herdadas, o isolamento exige sempre
  passar pela entidade pai. Ver `DATABASE_MAP.md` §1.
- Hierarquia: `tenant_ids_no_escopo` é o único caminho de visão
  cross-tenant (subárvore; `super_admin` vê tudo).
- Neo4j: nós carregam `tenant_id` na chave do `MERGE`.
- Shoal é **cross-tenant por desenho** (perfis, posts, conexões,
  intents, salas). A visibilidade é controlada por campos
  `visibilidade` (`publica|conexoes|privada`) e pelo status de conexão.
  É a área onde uma fronteira errada vaza dado de um tenant para outro.
- Testes: além dos pontuais (ex.: `test_isolamento_ia_critico.py`), a
  **varredura sistemática** `tests/integration/test_isolamento_sistematico.py`
  chama todas as rotas autenticadas como administrador de outro tenant,
  com ids reais da vítima, e confere leitura e mutação (matriz em
  `MATRIZ_ISOLAMENTO_ROTAS.md`). **RLS no banco: duas etapas prontas, ligadas só no staging** (D-110 e D-111, `RLS.md`): as 179 tabelas com dado de empresa têm política; em produção a API ainda conecta com o papel dono, que ignora o RLS.

## 3. Autenticação / autorização

- JWT HS256 com versão de sessão; redefinir senha invalida tokens anteriores.
- Navegadores usam cookie `HttpOnly` (`Secure; SameSite=None` em produção), não JWT persistido em `localStorage`. Mutação autenticada por cookie exige `Origin` autorizado; integrações podem usar Bearer.
- `validar_segredos_de_producao` recusa subir com `secret_key`/`jwt_secret_key` padrão ou sem `REDIS_URL` em produção.
- RBAC: 3 papéis + hierarquia + licença/módulo. **Sem ABAC** e sem
  policy engine. Checagens de "dono do recurso" (ex.: vendedor da
  conta) são feitas caso a caso em cada serviço.
- **Oportunidades CRM [corrigido]:** o campo explícito
  `negocio.vendedor_usuario_id` define o acesso do representante.
  `user` vê apenas oportunidades atribuídas ao próprio usuário; sem
  atribuição, só admin/super_admin as vê. Criador da conta e vendedor
  responsável pela conta não concedem acesso implícito à oportunidade.
  Apenas admin/super_admin pode atribuir/remover o representante; o
  backend valida usuário ativo com papel `user` no tenant da oportunidade
  e registra a alteração em auditoria. A atribuição também permite ler
  a conta e o contato diretamente vinculados àquela oportunidade, sem
  conceder permissão para editar ou excluir a conta.
- O gap de escalonamento via convite (2026-09-20) foi corrigido em
  `auth_service.gerar_convite`.
- **[novo]** Entitlement por router não bate com o módulo (C1, C3–C7 em
  `DOMAIN_DEPENDENCY_MAP.md`). Hoje isso causa **negação indevida**
  (403). O caso inverso também existe: um tenant só-CRM ganha as rotas
  de prospecção e enriquecimento do PREDATOR (C3). Esse é o lado de
  **concessão indevida**. O custo é limitado pelas franquias, mas não é zero.

## 4. Segredos

Credenciais de terceiros em repouso usam Fernet (`TextoCriptografado`).
A chave é obrigatória em produção. Rotação é manual. Webhooks verificam
a assinatura antes de ler o corpo. Inclui as chaves do envio por API de cada cliente
(`configuracao_email_api`, 2026-10): cifradas, mascaradas na resposta e com
chave pública própria para validar os avisos de entrega daquele tenant
(ver `08_SECURITY.md`).

## 5. IA

- **Human-in-the-loop** para comunicação externa: robusto e testado
  (ver `AI_CURRENT_STATE.md` §4).
- **[novo]** **Custo disparado por terceiros**: o call site #7
  (qualificação, via webhook inbound de WhatsApp/e-mail) e o #8 (Recall)
  chamam o LLM sem rate limit por tenant e sem medição. Um remetente
  externo consegue gerar custo de IA para um tenant.
- **[novo]** Só 3 de 14 call sites são medidos, e a medição é best-effort.
- Prompt injection: sem defesa estrutural. Exposição alta nos call
  sites #4 (HTML de site), #7 (mensagem de lead) e #8 (transcrição).
- RAG / vetores: não existem. O isolamento de RAG terá de nascer testado (§79).

## 6. Buy/Sell information barrier (§50, §80)

**Não aplicável hoje**: não existe nenhum dado de Procurement. Há dois
pontos de atenção para quando existir:

1. O Shoal já cruza dados entre tenants (`sinal_oportunidade_service`
   lê 8 modelos do Shoal). Dados Buy Side nunca podem entrar nesse caminho.
2. O modelo de tenancy atual é uma dimensão só (`tenant_id` + hierarquia).
   Uma barreira Buy/Sell exige pelo menos **classificação de dado** e
   **propósito** como eixos adicionais. Isso deve ser desenhado na Fase 2
   (modelo canônico), antes de qualquer tabela de Procurement.

## 7. Disponibilidade / abuso

- Rate limit usa Redis com janela deslizante atômica compartilhada quando `REDIS_URL` está configurado. Produção recusa iniciar sem Redis; o fallback em memória é só para dev/testes.
- Não há fila. Cron lento bloqueia a requisição.
- **[novo]** O CI (`.github/workflows/ci.yml`) só roda em `push`/`pull_request`
  para `master`. O desenvolvimento acontece em `staging`, e ali os
  testes **não rodam automaticamente**.

## 8. Auditoria / LGPD

`AuditLog` imutável, com escrita manual em cada mutação (a cobertura
depende de disciplina). LGPD: ROPA, supressão permanente, titulares com
expiração por cron, opt-out cancela mensagens pendentes.

## 9. Riscos priorizados

| # | Risco | Severidade | Fase que endereça |
|---|---|---|---|
| S1 | Isolamento só por disciplina, sem teste genérico cross-tenant | Alta | 1 (suite de regressão), 17 |
| S2 | IA não medida e disparada por terceiros (#7, #8) | Média | 4/5 |
| S3 | Prompt injection indireto (#4, #7, #8) | Média | 4 |
| S4 | Concessão de rotas PREDATOR a plano só-CRM (C3) | Baixa–Média | 1 |
| S5 | CI não roda em `staging` | Média (processo) | decisão do PO (OI-005) |
| S6 | Sem modelo de classificação de dado / propósito (pré-requisito da barreira Buy/Sell) | Alta (futuro) | **2, 10 (endereçado: D-034, fitness + teste §80)** |
| S7 | Aresta `privada` da rede visível para a empresa citada; qualquer usuário editava a identidade pública da empresa | Média | **7 (corrigido: D-026, D-027, `test_privacidade_rede.py`)** |
