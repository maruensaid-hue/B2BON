from sqlalchemy.orm import Session

from app.models.icp import ICP
from app.models.perfil_empresa import PerfilEmpresa
from app.services.errors import NaoEncontrado

_PESO_CNAE = 0.5
_PESO_UF = 0.3
_PESO_PORTE = 0.2


def calcular_fit_icp(icp: ICP, perfil_candidato: PerfilEmpresa) -> dict:
    """ICP Agent (master prompt §25, §60 ICP+Network, Fase 3B) — mesmos
    pesos de `conta_service._score_aderencia` (CNAE 0.5 + UF 0.3 +
    porte 0.2), aplicados contra o perfil de outro tenant da Rede
    Social em vez de uma `ContaCandidata` raspada. Nunca devolve um
    score isolado (§48) — sempre com `reasons`/`missing_data`."""
    pontuacao = 0.0
    reasons: list[str] = []
    missing_data: list[str] = []

    if perfil_candidato.cnae_principal:
        if perfil_candidato.cnae_principal in icp.cnae_codigos:
            pontuacao += _PESO_CNAE
            reasons.append(f"CNAE principal ({perfil_candidato.cnae_principal}) está entre os CNAEs do ICP.")
    else:
        missing_data.append("cnae_principal")

    if perfil_candidato.sede_uf:
        if perfil_candidato.sede_uf.upper() in {uf.upper() for uf in icp.ufs}:
            pontuacao += _PESO_UF
            reasons.append(f"Sede em {perfil_candidato.sede_uf} está entre as UFs do ICP.")
    else:
        missing_data.append("sede_uf")

    if perfil_candidato.porte:
        if icp.porte and perfil_candidato.porte == icp.porte:
            pontuacao += _PESO_PORTE
            reasons.append(f"Porte ({perfil_candidato.porte}) corresponde ao porte do ICP.")
    else:
        missing_data.append("porte")

    if len(missing_data) == 0:
        confidence = "alta"
    elif len(missing_data) == 1:
        confidence = "media"
    else:
        confidence = "baixa"

    return {
        "tenant_id_candidato": perfil_candidato.tenant_id,
        "empresa_nome": perfil_candidato.nome_exibicao,
        "fit_score": round(pontuacao, 2),
        "matched_icp": icp.nome,
        "reasons": reasons,
        "missing_data": missing_data,
        "confidence": confidence,
    }


def listar_fit_icp_rede(db: Session, tenant_id: str, icp_id: int) -> list[dict]:
    """Mostrar empresas da rede pertencentes a um ICP (master prompt
    §60) — compara o ICP do tenant que consulta contra o perfil
    público de todos os outros tenants da Rede Social."""
    icp = db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")

    perfis = db.query(PerfilEmpresa).filter(PerfilEmpresa.tenant_id != tenant_id).all()
    resultados = [calcular_fit_icp(icp, perfil) for perfil in perfis]
    resultados.sort(key=lambda resultado: resultado["fit_score"], reverse=True)
    return resultados
