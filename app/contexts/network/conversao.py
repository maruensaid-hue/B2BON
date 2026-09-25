"""Network → CRM e Network → PREDATOR (Fase 8, §51). GATE: sem duplicação.

Um sinal vira conta (e, no CRM, negócio) sem duplicar nada:

1. Conta: reaproveita a conta que o tenant já tem para aquela empresa (mesmo
   CNPJ, mesmo domínio, ou gerada por outro sinal da mesma empresa).
2. Negócio (destino `crm`): reaproveita o negócio aberto da conta.
3. Todos os sinais em aberto da mesma empresa-alvo são fechados juntos,
   apontando para a mesma conta/negócio; sinais que surgirem depois para
   essa empresa já nascem convertidos (`vincular_a_conversao_existente`).
"""

from sqlalchemy.orm import Session

from app.contexts.crm.contract import abrir_ou_reaproveitar_oportunidade
from app.contexts.network import identidade, privacidade
from app.contexts.shared.organizations import normalizar_dominio
from app.models.conta import Conta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.sinal_oportunidade import SinalOportunidade
from app.models.tenant import Tenant
from app.services import auditoria_service, conta_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

DESTINOS = ("crm", "predator")
_FINAIS = ("convertido", "descartado")


def _conta_existente(db: Session, tenant_id: str, alvo: str, cnpj: str | None, dominio: str | None) -> Conta | None:
    anterior = (
        db.query(SinalOportunidade)
        .filter(
            SinalOportunidade.tenant_id == tenant_id,
            SinalOportunidade.tenant_id_alvo == alvo,
            SinalOportunidade.conta_id_gerada.isnot(None),
        )
        .first()
    )
    if anterior is not None:
        conta = db.query(Conta).filter_by(id=anterior.conta_id_gerada, tenant_id=tenant_id).one_or_none()
        if conta is not None:
            return conta
    if cnpj:
        conta = db.query(Conta).filter_by(tenant_id=tenant_id, cnpj=cnpj).order_by(Conta.id).first()
        if conta is not None:
            return conta
    if dominio:
        return db.query(Conta).filter_by(tenant_id=tenant_id, dominio=dominio).order_by(Conta.id).first()
    return None


def converter(db: Session, tenant_id: str, ator_id: str | None, sinal_id: int, destino: str) -> dict:
    if destino not in DESTINOS:
        raise RegraNegocioViolada(f"Destino inválido: {destino}")
    sinal = db.query(SinalOportunidade).filter_by(id=sinal_id, tenant_id=tenant_id).one_or_none()
    if sinal is None:
        raise NaoEncontrado(f"Sinal de oportunidade {sinal_id} não encontrado")
    if sinal.status == "convertido":
        raise RegraNegocioViolada("Este sinal já foi convertido em uma conta do CRM.")
    if sinal.tenant_id_alvo in privacidade.bloqueados(db, tenant_id):
        raise RegraNegocioViolada("Há um bloqueio entre as empresas; o sinal não pode ser convertido.")

    tenant_alvo = db.query(Tenant).filter_by(id=sinal.tenant_id_alvo).one_or_none()
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=sinal.tenant_id_alvo).one_or_none()
    cnpj = identidade.normalizar_cnpj(tenant_alvo.cnpj if tenant_alvo else None)
    dominio = normalizar_dominio(perfil.site) if perfil is not None and perfil.site else None

    conta = _conta_existente(db, tenant_id, sinal.tenant_id_alvo, cnpj, dominio)
    conta_criada = conta is None
    if conta is None:
        conta = conta_service.criar_lead(
            db, tenant_id, ator_id,
            nome=perfil.nome_exibicao if perfil is not None else sinal.tenant_id_alvo,
            cnpj=cnpj, dominio=perfil.site if perfil is not None else None,
            segmento=perfil.setor if perfil is not None else None,
            porte=perfil.porte if perfil is not None else None,
            regiao=perfil.sede_uf if perfil is not None else None,
            origem="rede_social_signal",
        )

    negocio, negocio_criado = None, False
    if destino == "crm":
        negocio, negocio_criado = abrir_ou_reaproveitar_oportunidade(
            db, tenant_id, ator_id, conta.id, f"Oportunidade da rede — {conta.nome_fantasia or conta.nome}", "rede_signal"
        )

    irmaos = (
        db.query(SinalOportunidade)
        .filter(
            SinalOportunidade.tenant_id == tenant_id,
            SinalOportunidade.tenant_id_alvo == sinal.tenant_id_alvo,
            SinalOportunidade.status.notin_(_FINAIS),
        )
        .all()
    )
    for s in {sinal, *irmaos}:
        s.status = "convertido"
        s.conta_id_gerada = conta.id
        s.negocio_id_gerado = negocio.id if negocio is not None else s.negocio_id_gerado
        s.destino_conversao = destino

    auditoria_service.registrar(
        db, tenant_id, "sinal_oportunidade_convertido", "sinal_oportunidade", sinal.id, ator_id,
        {"conta_id": conta.id, "negocio_id": negocio.id if negocio else None, "destino": destino,
         "conta_reaproveitada": not conta_criada, "negocio_reaproveitado": negocio is not None and not negocio_criado},
    )
    db.commit()
    return {
        "conta_id": conta.id,
        "negocio_id": negocio.id if negocio is not None else None,
        "destino": destino,
        "conta_reaproveitada": not conta_criada,
        "negocio_reaproveitado": negocio is not None and not negocio_criado,
        "sinais_fechados": sorted(s.id for s in {sinal, *irmaos}),
    }


def vincular_a_conversao_existente(db: Session, tenant_id: str, sinal: SinalOportunidade) -> None:
    """Sinal novo de uma empresa já convertida nasce convertido (sem commit)."""
    anterior = (
        db.query(SinalOportunidade)
        .filter(
            SinalOportunidade.tenant_id == tenant_id,
            SinalOportunidade.tenant_id_alvo == sinal.tenant_id_alvo,
            SinalOportunidade.status == "convertido",
        )
        .first()
    )
    if anterior is not None:
        sinal.status = "convertido"
        sinal.conta_id_gerada = anterior.conta_id_gerada
        sinal.negocio_id_gerado = anterior.negocio_id_gerado
        sinal.destino_conversao = anterior.destino_conversao
