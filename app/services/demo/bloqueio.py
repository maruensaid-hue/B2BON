"""O que uma sessão de demonstração (D-082/D-083) pode acessar — política de NEGAÇÃO POR PADRÃO.

O ambiente é público e anônimo, então a regra é a inversa da plataforma: só passam as rotas das telas de produto
listadas em `PERMITIDAS` (os dados do próprio tenant fictício); todo o resto responde 403 — inclusive rotas que
venham a ser criadas no futuro, até alguém decidir liberá-las aqui. Dentro do permitido, ainda ficam bloqueadas as
escritas que gastam dinheiro, criam acesso ou falam com o mundo real (`ESCRITA_BLOQUEADA`).

Fora do permitido, entre outros: rede de empresas e sinais entre empresas (dados de clientes reais), administração da
plataforma (tenants, comissões, governo, representantes, FinOps, MAP Performance), usuários e convites, credenciais e
integrações (SMTP, WhatsApp, chaves de API, webhooks, CRMs, LinkedIn), pagamentos, LGPD e a API de parceiros.
"""

import re

API = "/api/v1"
# (prefixo, métodos permitidos) — "*" = leitura e escrita no próprio tenant fictício
PERMITIDAS: tuple[tuple[str, str], ...] = tuple((API + p, m) for p, m in (
    ("/auth/eu", "GET"), ("/auth/dispensar-banner-boas-vindas", "POST"), ("/auth/marcar-tutorial-modulo-visto", "POST"), ("/auth/preferencia-tema", "PUT"),
    ("/auth/demonstracao", "*"),
    ("/contas", "*"), ("/leads", "*"), ("/decisores", "*"), ("/icp", "*"), ("/ofertas", "*"), ("/listas-prospeccao", "*"),
    ("/crm", "*"), ("/cadencias", "*"), ("/campanhas", "*"), ("/aprovacoes", "*"), ("/envios", "*"), ("/reunioes", "*"),
    ("/conversas", "*"), ("/qualificacao", "*"), ("/comunicacao", "*"), ("/email-direto", "*"), ("/template-proposta", "*"),
    ("/regras-aprendidas", "*"), ("/saude-contas", "*"), ("/nps", "*"), ("/painel", "*"), ("/busca", "*"),
    ("/bids", "*"), ("/procurement", "*"), ("/sourcing", "*"), ("/agente-corporativo", "*"), ("/faq", "*"),
    ("/inteligencia/conhecimento", "*"), ("/inteligencia/perfil-empresa", "*"), ("/inteligencia/perfil-usuario", "*"),
    ("/inteligencia/aprendizado", "GET"), ("/inteligencia/agentes", "GET"), ("/inteligencia/features", "GET"),
    ("/inteligencia/receita", "GET"), ("/ai-credits", "GET"), ("/ai-credits/estimativas", "POST"),
    ("/relatorios", "GET"), ("/relatorio-entrega", "GET"), ("/onboarding", "GET"), ("/notificacoes", "GET"),
    ("/catalogo", "GET"), ("/assinatura", "GET"), ("/planos", "GET"),
))
ESCRITA_BLOQUEADA = (re.compile(rf"^{API}/sourcing/processos/\d+/(descoberta|participantes/\d+/acesso)$"),
                     re.compile(rf"^{API}/bids/ingestao"))
METODOS_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MENSAGEM = "Indisponível na demonstração: este recurso usa dados reais, gera custo ou envia algo para fora do ambiente fictício."


def _casa(caminho: str, prefixo: str) -> bool:
    return caminho == prefixo or caminho.startswith(prefixo + "/") or caminho.startswith(prefixo + "?")


def bloqueado(metodo: str, caminho: str) -> bool:
    metodo = metodo.upper()
    if metodo == "OPTIONS":
        return False
    for prefixo, metodos in PERMITIDAS:
        if _casa(caminho, prefixo) and (metodos == "*" or metodo in (metodos, "HEAD")):
            return metodo in METODOS_ESCRITA and any(r.match(caminho) for r in ESCRITA_BLOQUEADA)
    return True
