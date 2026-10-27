"""Guarda de CI (V5.2.1): toda rota SEM autenticação de sessão/chave precisa estar aprovada aqui, com a categoria que descreve o que a protege.

Uma rota pública nova quebra este teste até alguém classificá-la. Cada categoria tem uma verificação própria do mecanismo de proteção:
- cron: exige `_exigir_segredo_cron`;
- segredo_interno: exige `_exigir_segredo_interno` (`X-Webhook-Secret`);
- webhook_assinado / handshake_meta: validam assinatura/verify token dentro do handler (cobertos por testes próprios de assinatura);
- token_*: o segredo vai no caminho/cabeçalho e é resolvido pelo serviço (404 genérico);
- autenticacao: login/cadastro, com rate limit por IP (exceto logout);
- catalogo_publico: dado de plataforma sem tenant (preços, rótulos, catálogo) — nunca dado de cliente.
"""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

APROVADAS = {
    ("GET", "/api/v1/ai-credits/pacotes"): "catalogo_publico",
    ("GET", "/api/v1/ai-credits/workloads"): "catalogo_publico",
    ("GET", "/api/v1/auth/demonstracao"): "autenticacao",
    ("POST", "/api/v1/auth/demonstracao"): "autenticacao",
    ("POST", "/api/v1/auth/esqueci-senha"): "autenticacao",
    ("POST", "/api/v1/auth/google"): "autenticacao",
    ("POST", "/api/v1/auth/login"): "autenticacao",
    ("POST", "/api/v1/auth/logout"): "autenticacao",
    ("POST", "/api/v1/auth/redefinir-senha"): "autenticacao",
    ("POST", "/api/v1/auth/registrar"): "autenticacao",
    ("POST", "/api/v1/auth/registrar-publico"): "autenticacao",
    ("POST", "/api/v1/auth/registrar-vitrine"): "autenticacao",
    ("POST", "/api/v1/captura-lead/{codigo}"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/captura-lead/{codigo}/info"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/catalogo"): "catalogo_publico",
    ("GET", "/api/v1/central-negocios/mercado"): "catalogo_publico",
    ("GET", "/api/v1/central-negocios/noticias"): "catalogo_publico",
    ("GET", "/api/v1/convites/vitrine/{codigo}/info"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/hub-integracoes/oauth/{sistema}/callback"): "token_na_url_ou_cabecalho",
    ("POST", "/api/v1/hub-integracoes/webhook/{token}"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/opt-out/campanha/{token}"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/opt-out/email/{token}"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/planos"): "catalogo_publico",
    ("GET", "/api/v1/planos/enriquecimento"): "catalogo_publico",
    ("GET", "/api/v1/portal-fornecedor"): "token_na_url_ou_cabecalho",
    ("POST", "/api/v1/portal-fornecedor/declinar"): "token_na_url_ou_cabecalho",
    ("POST", "/api/v1/portal-fornecedor/perguntas"): "token_na_url_ou_cabecalho",
    ("POST", "/api/v1/portal-fornecedor/propostas"): "token_na_url_ou_cabecalho",
    ("POST", "/api/v1/portal-fornecedor/propostas/{proposta_id}/anexos"): "token_na_url_ou_cabecalho",
    ("GET", "/api/v1/representantes/self-service"): "catalogo_publico",
    ("GET", "/api/v1/rotulos-hierarquia"): "catalogo_publico",
    ("POST", "/api/v1/webhooks/email"): "segredo_interno",
    ("GET", "/api/v1/webhooks/email/aberto/{token}.png"): "token_hmac",
    ("POST", "/api/v1/webhooks/email/inbound"): "token_hmac",
    ("POST", "/api/v1/webhooks/mercadopago"): "webhook_assinado",
    ("POST", "/api/v1/webhooks/recall/eventos"): "webhook_assinado",
    ("POST", "/api/v1/webhooks/reputacao"): "segredo_interno",
    ("POST", "/api/v1/webhooks/envio/eventos"): "webhook_assinado",
    ("POST", "/api/v1/webhooks/sendgrid/eventos"): "webhook_assinado",
    ("POST", "/api/v1/webhooks/whatsapp"): "segredo_interno",
    ("GET", "/api/v1/webhooks/whatsapp/meta"): "handshake_meta",
    ("POST", "/api/v1/webhooks/whatsapp/meta"): "webhook_assinado",
    ("GET", "/health"): "catalogo_publico",
    **{("POST", f"/api/v1/cron/{nome}"): "cron" for nome in (
        "coletar-licitacoes", "creditos-ia", "disparar-relatorios-periodicos", "disparar-webhooks-parceiros", "enviar-lembretes-cobranca",
        "expirar-registros-oportunidade", "expirar-titulares", "integracoes-crm", "integracoes-crm-diario", "podar-historicos",
        "podar-recorte-cnpj", "processar-alertas-licitacoes", "processar-campanhas", "processar-envios", "processar-eventos", "processar-fila-enriquecimento",
        "processar-retorno", "repassar-comissoes", "sourcing-sincronizar", "suspender-licencas-vencidas",
    )},
}


def _inventario():
    spec = importlib.util.spec_from_file_location("inventario_rotas", RAIZ / "scripts" / "qualidade" / "inventario_rotas.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["inventario_rotas"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _publicas():
    return {(m, r.caminho): r for r in _inventario().carregar() if r.autenticacao == "nenhuma" for m in r.metodos}


def test_toda_rota_publica_esta_aprovada_e_toda_aprovada_ainda_existe():
    publicas = _publicas()

    novas = sorted(set(publicas) - set(APROVADAS))
    obsoletas = sorted(set(APROVADAS) - set(publicas))

    assert not novas, f"Rota(s) pública(s) sem aprovação/classificação (adicione em APROVADAS só após definir o que a protege): {novas}"
    assert not obsoletas, f"Rota(s) aprovada(s) que não são mais públicas ou deixaram de existir (remova de APROVADAS): {obsoletas}"


def test_cada_categoria_tem_o_mecanismo_de_protecao_que_declara():
    publicas = _publicas()
    for chave, categoria in APROVADAS.items():
        deps = " ".join(publicas[chave].deps)
        if categoria == "cron":
            assert "_exigir_segredo_cron" in deps, chave
        elif categoria == "segredo_interno":
            assert "_exigir_segredo_interno" in deps, chave
        elif categoria == "autenticacao" and chave not in {("GET", "/api/v1/auth/demonstracao"), ("POST", "/api/v1/auth/logout")}:
            assert "limitar" in deps, chave  # rate limit por IP/demonstração


def test_rotas_com_sessao_exigem_get_usuario_atual_e_nenhuma_aceita_tenant_do_cliente_sem_checagem_de_papel():
    """Rotas que recebem `tenant_id` do cliente no caminho/query só podem ser de super_admin, hierarquia verificada ou chave de parceiro."""
    sem_papel = []
    for rota in _inventario().carregar():
        if rota.autenticacao != "sessao" or not rota.params_tenant_do_cliente:
            continue
        if rota.papeis:  # exigir_papel(...)
            continue
        sem_papel.append(f"{'|'.join(rota.metodos)} {rota.caminho} {rota.params_tenant_do_cliente}")
    # Estas verificam a hierarquia/conexão dentro do serviço (cobertas por test_isolamento_hierarquia e test_isolamento_sistematico).
    esperadas = {
        "DELETE /api/v1/admin/tenants/{tenant_id}", "POST /api/v1/admin/tenants/{tenant_id}/desativar", "GET /api/v1/admin/tenants/{tenant_id}/licenca",
        "PUT /api/v1/admin/tenants/{tenant_id}/licenca", "POST /api/v1/admin/tenants/{tenant_id}/reativar",
        "POST /api/v1/inteligencia-rede/intents/{intent_id}/matches/{tenant_id_candidato}/explicar-com-ia",
        "GET /api/v1/leads/contas", "POST /api/v1/rede-social/bloquear/{tenant_id_outro}", "GET /api/v1/rede-social/mensagens/{com_tenant_id}",
        "GET /api/v1/rede-social/relacionamentos/{tenant_id_alvo}", "DELETE /api/v1/rede-social/seguir/{tenant_id_seguido}",
        "GET /api/v1/registro-oportunidade", "GET /api/v1/saude-contas/dashboard", "GET /api/v1/saude-contas/ranking",
    }
    inesperadas = sorted(r for r in sem_papel if r.split(" [")[0] not in esperadas)
    assert not inesperadas, f"Rota nova recebe tenant do cliente sem exigir papel; revise o escopo e, se correto, adicione em `esperadas`: {inesperadas}"
