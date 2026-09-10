from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.negocio import Negocio
from app.models.proposta_negocio import PropostaNegocio
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.schemas.busca import ResultadoBuscaSchema
from app.services import tenant_service

_TAMANHO_MINIMO_TERMO = 2
_LIMITE_POR_TIPO = 8
_LIMITE_TENANTS = 5


def _pode_ver_tenants(db: Session, usuario: Usuario) -> bool:
    """Mesmo critério de `deps.permitir_gestao_hierarquica`, mas devolvendo
    um booleano em vez de levantar exceção — aqui é só um "inclui ou não
    esse tipo de resultado", não um bloqueio de rota."""
    if usuario.papel == "super_admin":
        return True
    if usuario.papel != "admin":
        return False
    tenant_do_usuario = db.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none()
    return tenant_do_usuario is not None and tenant_do_usuario.tipo in {"distribuidor", "revendedor"}


def buscar(db: Session, usuario: Usuario, termo: str) -> list[ResultadoBuscaSchema]:
    termo = termo.strip()
    # Termo numérico (nº de proposta) é busca exata, não substring — não
    # precisa do mínimo de caracteres que evita um "a" solto varrer tudo.
    if not termo or (len(termo) < _TAMANHO_MINIMO_TERMO and not termo.isdigit()):
        return []
    padrao = f"%{termo}%"
    tenant_id = usuario.tenant_id
    resultados: list[ResultadoBuscaSchema] = []

    contas = (
        db.query(Conta)
        .filter(
            Conta.tenant_id == tenant_id,
            or_(
                Conta.nome.ilike(padrao),
                Conta.nome_fantasia.ilike(padrao),
                Conta.cnpj.ilike(padrao),
                Conta.dominio.ilike(padrao),
            ),
        )
        .order_by(Conta.nome)
        .limit(_LIMITE_POR_TIPO)
        .all()
    )
    for conta in contas:
        resultados.append(
            ResultadoBuscaSchema(
                tipo="conta",
                id=conta.id,
                titulo=conta.nome,
                subtitulo=conta.cnpj,
                rota=f"/leads/contas/{conta.id}",
            )
        )

    negocios = (
        db.query(Negocio)
        .join(Conta, Conta.id == Negocio.conta_id)
        .filter(
            Negocio.tenant_id == tenant_id,
            or_(Negocio.nome.ilike(padrao), Conta.nome.ilike(padrao)),
        )
        .order_by(Negocio.nome)
        .limit(_LIMITE_POR_TIPO)
        .all()
    )
    for negocio in negocios:
        conta = db.query(Conta).filter_by(id=negocio.conta_id).one_or_none()
        resultados.append(
            ResultadoBuscaSchema(
                tipo="negocio",
                id=negocio.id,
                titulo=negocio.nome,
                subtitulo=conta.nome if conta else None,
                rota=f"/crm?negocio_id={negocio.id}",
            )
        )

    filtros_proposta = [PropostaNegocio.nome.ilike(padrao), Negocio.nome.ilike(padrao), Conta.nome.ilike(padrao)]
    if termo.isdigit():
        filtros_proposta.append(PropostaNegocio.numero == int(termo))
    propostas = (
        db.query(PropostaNegocio)
        .join(Negocio, Negocio.id == PropostaNegocio.negocio_id)
        .join(Conta, Conta.id == Negocio.conta_id)
        .filter(PropostaNegocio.tenant_id == tenant_id, or_(*filtros_proposta))
        .order_by(PropostaNegocio.criado_em.desc())
        .limit(_LIMITE_POR_TIPO)
        .all()
    )
    for proposta in propostas:
        negocio = db.query(Negocio).filter_by(id=proposta.negocio_id).one_or_none()
        if proposta.nome:
            titulo = proposta.nome
        elif proposta.numero:
            titulo = f"Proposta #{proposta.numero}"
        else:
            titulo = proposta.nome_arquivo
        resultados.append(
            ResultadoBuscaSchema(
                tipo="proposta",
                id=proposta.id,
                titulo=titulo,
                subtitulo=negocio.nome if negocio else None,
                rota=f"/crm?negocio_id={proposta.negocio_id}",
            )
        )

    decisores = (
        db.query(Decisor)
        .join(Conta, Conta.id == Decisor.conta_id)
        .filter(
            Decisor.tenant_id == tenant_id,
            or_(Decisor.nome.ilike(padrao), Decisor.email.ilike(padrao), Decisor.cargo.ilike(padrao)),
        )
        .order_by(Decisor.nome)
        .limit(_LIMITE_POR_TIPO)
        .all()
    )
    for decisor in decisores:
        conta = db.query(Conta).filter_by(id=decisor.conta_id).one_or_none()
        subtitulo_partes = [parte for parte in [decisor.cargo, conta.nome if conta else None] if parte]
        resultados.append(
            ResultadoBuscaSchema(
                tipo="decisor",
                id=decisor.id,
                titulo=decisor.nome,
                subtitulo=" · ".join(subtitulo_partes) if subtitulo_partes else None,
                rota=f"/leads/contas/{decisor.conta_id}",
            )
        )

    cadencias = (
        db.query(Cadencia)
        .filter(Cadencia.tenant_id == tenant_id, Cadencia.nome.ilike(padrao))
        .order_by(Cadencia.nome)
        .limit(_LIMITE_POR_TIPO)
        .all()
    )
    for cadencia in cadencias:
        resultados.append(
            ResultadoBuscaSchema(
                tipo="cadencia",
                id=cadencia.id,
                titulo=cadencia.nome,
                subtitulo=cadencia.tipo,
                rota=f"/cadencias?cadencia_id={cadencia.id}",
            )
        )

    if _pode_ver_tenants(db, usuario):
        tenants_visiveis = tenant_service.listar_tenants_visiveis(db, usuario)
        termo_lower = termo.lower()
        tenants_encontrados = [
            tenant
            for tenant in tenants_visiveis
            if termo_lower in tenant.razao_social.lower()
            or termo_lower in tenant.id.lower()
            or (tenant.cnpj is not None and termo_lower in tenant.cnpj.lower())
        ][:_LIMITE_TENANTS]
        for tenant in tenants_encontrados:
            resultados.append(
                ResultadoBuscaSchema(
                    tipo="tenant",
                    id=tenant.id,
                    titulo=tenant.razao_social,
                    subtitulo=tenant.id,
                    rota="/admin/tenants",
                )
            )

    return resultados
