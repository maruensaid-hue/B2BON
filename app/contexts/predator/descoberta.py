"""Descoberta de empresas por busca de mapa: acha quem o recorte de CNPJ não mostra (presença digital, posição, nota, empresa sem site).

É a única etapa da prospecção que cobra por chamada, por isso ela sempre estima antes e só executa com o custo confirmado pela pessoa
(o valor confirmado precisa bater com a estimativa daquele pedido). Sem chave configurada, não existe: nada é inventado nem cobrado.
Cada empresa achada vira conta (`origem="descoberta_busca"`) com os sinais da busca; a que já existe no tenant (mesmo domínio, ou mesmo
nome sem domínio) só recebe os sinais novos. Ficha que aponta para rede social ou diretório conta como "sem site".
"""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.predator import sinais
from app.contexts.predator.prospeccao import enfileirar_enriquecimento_em_lote
from app.contexts.shared.organizations import normalizar_dominio
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


@dataclass
class Estimativa:
    buscas: int
    custo_usd: float
    configurado: bool


def _termos_e_cidades(termos: list[str], cidades: list[str]) -> tuple[list[str], list[str]]:
    termos = [t.strip() for t in termos if t and t.strip()]
    cidades = [c.strip() for c in cidades if c and c.strip()]
    if not termos or not cidades:
        raise ValidacaoFalhou("Informe ao menos um termo (o que a empresa faz) e uma cidade.")
    return termos, cidades


def estimar(provedor: DescobertaEmpresasProvider, termos: list[str], cidades: list[str], max_buscas: int) -> Estimativa:
    termos, cidades = _termos_e_cidades(termos, cidades)
    buscas = len(termos) * len(cidades)
    if buscas > max_buscas:
        raise ValidacaoFalhou(f"{buscas} buscas passam do teto de {max_buscas} por execução: reduza termos ou cidades.")
    return Estimativa(buscas=buscas, custo_usd=round(buscas * provedor.custo_por_busca_usd, 4), configurado=provedor.configurado)


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
    custo_confirmado_usd: float,
    max_buscas: int,
    icp_id: int | None = None,
    limite_por_busca: int = 20,
) -> dict:
    """Roda as buscas (termos x cidades) e cria/atualiza as contas. Exige o custo confirmado igual ao estimado para este pedido."""
    estimativa = estimar(provedor, termos, cidades, max_buscas)
    if not estimativa.configurado:
        raise RegraNegocioViolada("A descoberta por busca não está configurada nesta instalação.")
    if not math.isclose(custo_confirmado_usd, estimativa.custo_usd, abs_tol=1e-6):
        raise RegraNegocioViolada(
            f"Confirme o custo estimado (US$ {estimativa.custo_usd:.4f} por {estimativa.buscas} busca(s)) antes de executar."
        )
    termos, cidades = _termos_e_cidades(termos, cidades)

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
        db, tenant_id, "descoberta_busca_executada", "icp" if icp_id else "tenant", icp_id or 0, ator_id,
        {"buscas": buscas_feitas, "custo_estimado_usd": estimativa.custo_usd, "criadas": criadas, "atualizadas": atualizadas, "falhas": len(falhas)},
    )
    db.commit()
    # Conta nova com site entra sozinha na fila de enriquecimento (o cron lê o site, grava os sinais e mapeia os decisores), como no
    # import de planilha: descobrir e ler o site são um passo só para quem usa.
    enfileiradas = enfileirar_enriquecimento_em_lote(db, tenant_id, novas_com_site)["contas_enfileiradas"] if novas_com_site else 0
    return {"buscas": buscas_feitas, "criadas": criadas, "atualizadas": atualizadas, "enfileiradas": enfileiradas, "falhas": falhas}
