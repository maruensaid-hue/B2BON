"""Company Identity e Company Claim (Fase 7, §27).

Cada tenant da rede tem uma identidade (`empresa_rede`). Uma empresa que
ainda não é cliente pode ser citada por CNPJ (ex.: "somos fornecedores
da ACME"): nasce NAO_REIVINDICADA, só com CNPJ e nome. Quando a própria
empresa entra na B2B ON, é verificada e tem o mesmo CNPJ, ela reivindica
essa identidade: tudo que apontava para ela passa a apontar para o tenant.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.empresa_rede import EmpresaRede
from app.models.perfil_empresa import PerfilEmpresa
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.models.tenant import Tenant
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou


def normalizar_cnpj(cnpj: str | None) -> str | None:
    digitos = "".join(c for c in (cnpj or "") if c.isdigit())
    return digitos or None


def cnpj_valido(cnpj: str | None) -> bool:
    digitos = normalizar_cnpj(cnpj)
    if not digitos or len(digitos) != 14 or len(set(digitos)) == 1:
        return False

    def dv(base: str) -> str:
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    return digitos[12] == dv(digitos[:12]) and digitos[13] == dv(digitos[:13])


def garantir_do_tenant(db: Session, tenant_id: str) -> EmpresaRede:
    """Identidade do tenant, criada na primeira vez (flush, sem commit)."""
    empresa = db.query(EmpresaRede).filter_by(tenant_id=tenant_id).one_or_none()
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    status = "VERIFICADA" if perfil is not None and perfil.status_verificacao == "verificada" else "REIVINDICADA"
    if empresa is not None:
        if empresa.status != status:
            empresa.status = status
        if perfil is not None and perfil.nome_exibicao and empresa.nome_exibicao != perfil.nome_exibicao:
            empresa.nome_exibicao = perfil.nome_exibicao
        return empresa
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        raise NaoEncontrado(f"Empresa {tenant_id} não encontrada")
    empresa = EmpresaRede(
        tenant_id=tenant_id,
        cnpj=normalizar_cnpj(tenant.cnpj),
        razao_social=tenant.razao_social,
        nome_exibicao=(perfil.nome_exibicao if perfil is not None else None) or tenant.razao_social or tenant_id,
        status=status,
        origem="TENANT",
    )
    db.add(empresa)
    db.flush()
    return empresa


def por_cnpj(db: Session, cnpj: str, nome: str | None, criado_por_tenant_id: str) -> EmpresaRede:
    """Identidade para um CNPJ: a do tenant dono, se já estiver na rede;
    senão, uma NAO_REIVINDICADA (reaproveitada se já citada antes)."""
    if not cnpj_valido(cnpj):
        raise ValidacaoFalhou("CNPJ inválido.")
    digitos = normalizar_cnpj(cnpj)
    candidatas = db.query(EmpresaRede).filter(EmpresaRede.cnpj == digitos, EmpresaRede.status != "MESCLADA").all()
    reivindicada = next((e for e in candidatas if e.tenant_id is not None), None)
    if reivindicada is not None:
        return reivindicada
    if candidatas:
        return candidatas[0]
    empresa = EmpresaRede(
        tenant_id=None, cnpj=digitos, razao_social=None,
        nome_exibicao=(nome or "").strip()[:200] or f"CNPJ {digitos}",
        status="NAO_REIVINDICADA", origem="DECLARADA_POR_TERCEIRO", criado_por_tenant_id=criado_por_tenant_id,
    )
    db.add(empresa)
    db.flush()
    return empresa


def reivindicaveis(db: Session, tenant_id: str) -> list[EmpresaRede]:
    """Identidades não reivindicadas com o CNPJ deste tenant."""
    propria = garantir_do_tenant(db, tenant_id)
    if not propria.cnpj:
        return []
    return db.query(EmpresaRede).filter_by(cnpj=propria.cnpj, status="NAO_REIVINDICADA").all()


def reivindicar(db: Session, tenant_id: str, empresa_id: int) -> EmpresaRede:
    """Company Claim. Exige empresa verificada pela plataforma e CNPJ igual."""
    propria = garantir_do_tenant(db, tenant_id)
    alvo = db.query(EmpresaRede).filter_by(id=empresa_id).one_or_none()
    if alvo is None or alvo.status != "NAO_REIVINDICADA":
        raise NaoEncontrado(f"Empresa {empresa_id} não encontrada ou já reivindicada")
    if propria.status != "VERIFICADA":
        raise RegraNegocioViolada("Só empresa verificada pode reivindicar uma identidade na rede. Solicite a verificação.")
    if not propria.cnpj or propria.cnpj != alvo.cnpj:
        raise NaoAutorizado("O CNPJ desta empresa não confere com a identidade reivindicada.")

    for aresta in db.query(RelacionamentoEmpresarial).filter_by(empresa_destino_id=alvo.id).all():
        if aresta.tenant_id_origem == tenant_id:
            db.delete(aresta)  # a empresa não se relaciona consigo mesma
            continue
        aresta.empresa_destino_id = propria.id
        aresta.tenant_id_destino = tenant_id
    alvo.status = "MESCLADA"
    alvo.mesclada_em_id = propria.id
    propria.reivindicada_em = datetime.now(UTC)
    db.flush()
    return propria


def como_dict(empresa: EmpresaRede) -> dict:
    """Só dado de identidade pública: nunca dado de CRM do tenant."""
    return {
        "id": empresa.id,
        "tenant_id": empresa.tenant_id,
        "cnpj": empresa.cnpj,
        "nome_exibicao": empresa.nome_exibicao,
        "status": empresa.status,
        "origem": empresa.origem,
    }


def perfil_publico_por_cnpj(db: Session, cnpj: str | None) -> dict | None:
    """Perfil público de uma empresa da rede pelo CNPJ (Fase 10: Supplier 360
    do comprador). Só campos públicos, só se a empresa estiver no diretório.
    Leitura: não cria identidade."""
    digitos = normalizar_cnpj(cnpj)
    if not digitos:
        return None
    empresa = (
        db.query(EmpresaRede)
        .filter(EmpresaRede.cnpj == digitos, EmpresaRede.tenant_id.isnot(None), EmpresaRede.status != "MESCLADA")
        .first()
    )
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=empresa.tenant_id).one_or_none() if empresa else None
    if perfil is None or not perfil.visivel_no_diretorio:
        return None
    return {
        "origem": "SELF_DECLARED",
        "fonte": "B2B ON Business Network (perfil público)",
        "nome_exibicao": perfil.nome_exibicao,
        "setor": perfil.setor,
        "site": perfil.site,
        "porte": perfil.porte,
        "sede_uf": perfil.sede_uf,
        "produtos_servicos": perfil.produtos_servicos or [],
        "tecnologias": perfil.tecnologias or [],
        "certificacoes": perfil.certificacoes or [],
        "verificada_pela_plataforma": empresa.status == "VERIFICADA",
    }
