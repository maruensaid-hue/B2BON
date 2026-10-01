"""O que uma sessão de demonstração (D-082) não pode fazer — o ambiente é público e anônimo.

- Bloqueio total (inclusive leitura): tudo que mostra dados de outros clientes (rede de empresas, sinais de
  oportunidade entre empresas, indicações) ou é administração da plataforma (comissões, governo, representantes,
  FinOps, MAP Performance, motor de tenants, LGPD).
- Bloqueio de escrita: o que gasta dinheiro, cria acesso ou fala com o mundo real — pagamento e compra de créditos,
  usuários e convites, credenciais (SMTP, WhatsApp, chaves de API, webhooks, integrações de CRM, LinkedIn), coleta
  externa (PNCP), descoberta de fornecedores na rede e acesso de fornecedor ao portal.
E-mail e WhatsApp de cadências e campanhas continuam funcionando — saem por provedores simulados (`deps.resolver_*`).
"""

import re

API = "/api/v1"
BLOQUEIO_TOTAL = tuple(API + p for p in (
    "/rede-social", "/inteligencia-rede", "/central-negocios", "/rede/convites-sourcing", "/indicacoes", "/inteligencia/oportunidades",
    "/admin", "/representantes", "/comissoes", "/governo", "/map/performance", "/motor", "/finops", "/ropa", "/titulares",
    "/registro-oportunidade", "/rotulos-hierarquia",
))
BLOQUEIO_ESCRITA = tuple(API + p for p in (
    "/usuarios", "/convites", "/planos", "/ai-credits/compras", "/ai-credits/recarga-automatica", "/ai-credits/orcamento",
    "/configuracao-email-smtp", "/configuracao-whatsapp", "/configuracao-envio", "/linkedin", "/integracoes", "/chaves-api",
    "/webhooks-saida", "/captura-lead", "/portal-fornecedor", "/bids/ingestao",
    "/auth/declarar-pagamento", "/auth/whatsapp-pessoal", "/auth/registrar",
))
ESCRITA_REGEX = (re.compile(rf"^{API}/sourcing/processos/\d+/(descoberta|participantes/\d+/acesso)$"),)
METODOS_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MENSAGEM = "Indisponível na demonstração: este recurso usa dados reais, gera custo ou envia algo para fora do ambiente fictício."


def bloqueado(metodo: str, caminho: str) -> bool:
    if caminho.startswith(BLOQUEIO_TOTAL):
        return True
    if metodo.upper() not in METODOS_ESCRITA:
        return False
    return caminho.startswith(BLOQUEIO_ESCRITA) or any(r.match(caminho) for r in ESCRITA_REGEX)
