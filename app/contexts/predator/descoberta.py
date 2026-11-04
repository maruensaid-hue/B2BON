"""Descoberta de empresas por busca de mapa: acha quem o recorte de CNPJ não mostra (presença digital, posição, nota, empresa sem site).

Sempre estima antes e só executa com o número de buscas confirmado pela pessoa (precisa bater com a estimativa daquele pedido). Para o
cliente, cada busca é consumo da franquia do mês (nunca aparece custo nem a fonte): assim a troca da base aberta de mapas por uma fonte
paga não muda a regra para ele. O custo interno da fonte fica só na auditoria.
Cada empresa achada vira conta (`origem="descoberta_busca"`) com os sinais da busca; a que já existe no tenant (mesmo domínio, ou mesmo
nome sem domínio) só recebe os sinais novos. Ficha que aponta para rede social ou diretório conta como "sem site".
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.predator import sinais
from app.contexts.predator.prospeccao import enfileirar_enriquecimento_em_lote
from app.contexts.shared.organizations import normalizar_dominio
from app.models.auditoria import AuditLog
from app.models.conta import Conta
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider, DescobertaIndisponivel, EmpresaDescoberta
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

# Rede social, diretório, marketplace e governo: não é o site da empresa.
_NAO_E_SITE = re.compile(
    r"(?:^|\.)(?:facebook|instagram|linkedin|twitter|x|tiktok|youtube|wa|whatsapp|linktr|google|goo|g|bit|wikipedia|ifood|doctoralia|"
    r"guiamais|telelistas|apontador|yelp|tripadvisor|mercadolivre|olx|reclameaqui|booking|airbnb|gov|jusbrasil|econodata|cnpj|"
    r"solutudo|cylex|hotfrog|encontra[a-z]*)\.",
    re.IGNORECASE,
)


_EVENTO = "descoberta_busca_executada"


@dataclass
class Estimativa:
    buscas: int
    custo_usd: float  # custo interno da fonte: só para a auditoria, nunca vai ao cliente
    configurado: bool
    usadas_no_mes: int = 0
    franquia_mensal: int = 0  # 0 = sem limite definido


def _inicio_do_mes_utc(agora: datetime) -> datetime:
    """Início do mês de Brasília (UTC-3), em UTC sem fuso, como o banco guarda `criado_em`."""
    local = agora.astimezone(UTC).replace(tzinfo=None) - timedelta(hours=3)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=3)


def usadas_no_mes(db: Session, tenant_id: str, agora: datetime | None = None) -> int:
    """Buscas feitas pela empresa no mês corrente (as que falharam não contam)."""
    inicio = _inicio_do_mes_utc(agora or datetime.now(UTC))
    registros = db.query(AuditLog.detalhes).filter(
        AuditLog.tenant_id == tenant_id, AuditLog.evento_tipo == _EVENTO, AuditLog.criado_em >= inicio
    ).all()
    return sum(int((detalhes or {}).get("buscas") or 0) for (detalhes,) in registros)


def _termos_e_cidades(termos: list[str], cidades: list[str]) -> tuple[list[str], list[str]]:
    termos = [t.strip() for t in termos if t and t.strip()]
    cidades = [c.strip() for c in cidades if c and c.strip()]
    if not termos or not cidades:
        raise ValidacaoFalhou("Informe ao menos um termo (o que a empresa faz) e uma cidade.")
    return termos, cidades


def estimar(
    provedor: DescobertaEmpresasProvider, termos: list[str], cidades: list[str], max_buscas: int,
    db: Session | None = None, tenant_id: str | None = None, franquia_mensal: int = 0,
) -> Estimativa:
    termos, cidades = _termos_e_cidades(termos, cidades)
    buscas = len(termos) * len(cidades)
    if buscas > max_buscas:
        raise ValidacaoFalhou(f"{buscas} buscas passam do teto de {max_buscas} por execução: reduza termos ou cidades.")
    usadas = usadas_no_mes(db, tenant_id) if db is not None and tenant_id else 0
    return Estimativa(
        buscas=buscas, custo_usd=round(buscas * provedor.custo_por_busca_usd, 4), configurado=provedor.configurado,
        usadas_no_mes=usadas, franquia_mensal=max(franquia_mensal, 0),
    )


def _site_proprio(site: str | None) -> str | None:
    dominio = normalizar_dominio(site)
    if not dominio or _NAO_E_SITE.search(dominio + "."):
        return None
    return re.sub(r"^www\.", "", dominio.lower())


def _chave_nome(nome: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii").lower())


def _gravar_sinais(db: Session, tenant_id: str, conta_id: int, achada: EmpresaDescoberta, sem_site: bool, agora: datetime) -> None:
    def gravar(codigo: str, **valores) -> None:
        sinais._gravar(db, tenant_id, conta_id, codigo, confianca=0.9, fonte="descoberta_busca", agora=agora, **valores)

    gravar("POSICAO_MAPA", num=achada.posicao, texto=achada.busca[:200])
    if achada.nota is not None:
        gravar("NOTA_AVALIACOES", num=float(achada.nota))
    if achada.avaliacoes is not None:
        gravar("QTD_AVALIACOES", num=int(achada.avaliacoes))
    gravar("SEM_SITE", num=1 if sem_site else 0, url=achada.site)


def executar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    provedor: DescobertaEmpresasProvider,
    termos: list[str],
    cidades: list[str],
    buscas_confirmadas: int,
    max_buscas: int,
    icp_id: int | None = None,
    limite_por_busca: int = 20,
    franquia_mensal: int = 0,
) -> dict:
    """Roda as buscas (termos x cidades) e cria/atualiza as contas. Exige o número de buscas confirmado igual ao estimado e, com franquia
    definida, que caiba no que resta dela no mês."""
    estimativa = conferir_pedido(db, tenant_id, provedor, termos, cidades, buscas_confirmadas, max_buscas, franquia_mensal)
    termos, cidades = _termos_e_cidades(termos, cidades)
    return _rodar(db, tenant_id, ator_id, provedor, termos, cidades, estimativa, icp_id, limite_por_busca)


def conferir_pedido(
    db: Session, tenant_id: str, provedor: DescobertaEmpresasProvider, termos: list[str], cidades: list[str],
    buscas_confirmadas: int, max_buscas: int, franquia_mensal: int = 0,
) -> Estimativa:
    """Tudo o que precisa valer antes de chamar a fonte (disponível, buscas confirmadas, franquia). Usado também antes de mandar a
    execução para o segundo plano, para a recusa aparecer na hora."""
    estimativa = estimar(provedor, termos, cidades, max_buscas, db, tenant_id, franquia_mensal)
    if not estimativa.configurado:
        raise RegraNegocioViolada("A descoberta por busca não está disponível nesta instalação.")
    if buscas_confirmadas != estimativa.buscas:
        raise RegraNegocioViolada(f"Confirme as {estimativa.buscas} busca(s) estimadas antes de executar.")
    if estimativa.franquia_mensal and estimativa.usadas_no_mes + estimativa.buscas > estimativa.franquia_mensal:
        restam = max(estimativa.franquia_mensal - estimativa.usadas_no_mes, 0)
        raise RegraNegocioViolada(
            f"A franquia do mês tem {restam} busca(s) restante(s) e este pedido usa {estimativa.buscas}: reduza termos ou cidades."
        )
    return estimativa


def _rodar(
    db: Session, tenant_id: str, ator_id: str | None, provedor: DescobertaEmpresasProvider, termos: list[str], cidades: list[str],
    estimativa: Estimativa, icp_id: int | None, limite_por_busca: int,
) -> dict:

    contas = db.query(Conta).filter(Conta.tenant_id == tenant_id).all()
    por_dominio = {re.sub(r"^www\.", "", c.dominio.lower()): c for c in contas if c.dominio}
    por_nome = {_chave_nome(c.nome_fantasia or c.nome): c for c in contas}
    agora = datetime.now(UTC)
    criadas = atualizadas = buscas_feitas = 0
    novas_com_site: list[int] = []
    falhas: list[str] = []
    for termo in termos:
        for cidade in cidades:
            try:
                achadas = provedor.buscar(termo, cidade, limite_por_busca)
            except DescobertaIndisponivel as erro:
                falhas.append(f"{termo} / {cidade}: {erro}")
                continue
            buscas_feitas += 1
            for achada in achadas:
                dominio = _site_proprio(achada.site)
                conta = (por_dominio.get(dominio) if dominio else None) or por_nome.get(_chave_nome(achada.nome))
                if conta is None:
                    conta = Conta(
                        tenant_id=tenant_id, icp_id=icp_id, nome=achada.nome, dominio=dominio, status="prospectada",
                        origem="descoberta_busca", regiao=cidade[:80], segmento=(achada.categoria or termo)[:120],
                        observacoes="\n".join(v for v in (achada.endereco, achada.telefone and f"Telefone: {achada.telefone}") if v) or None,
                    )
                    db.add(conta)
                    db.flush()
                    criadas += 1
                    if dominio:
                        por_dominio[dominio] = conta
                        novas_com_site.append(conta.id)
                    por_nome[_chave_nome(achada.nome)] = conta
                else:
                    atualizadas += 1
                _gravar_sinais(db, tenant_id, conta.id, achada, sem_site=dominio is None, agora=agora)

    auditoria_service.registrar(
        db, tenant_id, _EVENTO, "icp" if icp_id else "tenant", icp_id or 0, ator_id,
        {"buscas": buscas_feitas, "custo_estimado_usd": estimativa.custo_usd, "criadas": criadas, "atualizadas": atualizadas, "falhas": len(falhas)},
    )
    db.commit()
    # Conta nova com site entra sozinha na fila de enriquecimento (o cron lê o site, grava os sinais e mapeia os decisores), como no
    # import de planilha: descobrir e ler o site são um passo só para quem usa.
    enfileiradas = enfileirar_enriquecimento_em_lote(db, tenant_id, novas_com_site)["contas_enfileiradas"] if novas_com_site else 0
    return {"buscas": buscas_feitas, "criadas": criadas, "atualizadas": atualizadas, "enfileiradas": enfileiradas, "falhas": falhas}
