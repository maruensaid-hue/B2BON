"""Tax Profile (D-074): carga tributária atribuível à receita, parametrizada pelo PO com vigência. Regime informado
pelo PO: Lucro Presumido — a alíquota vem do perfil, nunca do código."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import QUALQUER
from app.models.apuracao_comissao import PerfilTributario
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CENTAVO = Decimal("0.01")


def aplicavel(db: Session, tipo_receita: str, dia: date) -> PerfilTributario | None:
    """Perfil vigente no dia, específico do tipo de receita antes do genérico ("*")."""
    candidatos = db.query(PerfilTributario).filter(
        PerfilTributario.vigente_de <= dia, or_(PerfilTributario.vigente_ate.is_(None), PerfilTributario.vigente_ate > dia),
        PerfilTributario.tipo_receita.in_((tipo_receita, QUALQUER)),
    ).all()
    candidatos.sort(key=lambda p: (p.tipo_receita == QUALQUER, -p.vigente_de.toordinal(), -p.id))
    return candidatos[0] if candidatos else None


def imposto(perfil: PerfilTributario, bruto: Decimal) -> Decimal:
    return (bruto * Decimal(str(perfil.aliquota_efetiva))).quantize(CENTAVO, ROUND_HALF_UP)


def criar(db: Session, dados: dict, ator_id: str | None) -> PerfilTributario:
    componentes = dados.get("componentes") or []
    if not componentes or any(not c.get("nome") or c.get("aliquota") is None or not 0 <= float(c["aliquota"]) < 1 for c in componentes):
        raise ValidacaoFalhou("Informe os componentes do perfil (nome e alíquota entre 0 e 1).")
    efetiva = dados.get("aliquota_efetiva")
    if efetiva is None:
        efetiva = float(sum(Decimal(str(c["aliquota"])) for c in componentes))
    if not 0 <= efetiva < 1:
        raise ValidacaoFalhou("Alíquota efetiva entre 0 e 1.")
    vigente_de, vigente_ate = dados["vigente_de"], dados.get("vigente_ate")
    if vigente_ate is not None and vigente_ate <= vigente_de:
        raise ValidacaoFalhou("O fim da vigência precisa ser depois do início.")
    tipo = dados.get("tipo_receita") or QUALQUER
    municipio = dados.get("municipio")
    for aberto in db.query(PerfilTributario).filter_by(tipo_receita=tipo, municipio=municipio, vigente_ate=None).all():
        if aberto.vigente_de >= vigente_de:
            raise ValidacaoFalhou(f"Já existe perfil para {tipo} vigente desde {aberto.vigente_de}; encerre-o antes.")
        aberto.vigente_ate = vigente_de  # o novo perfil substitui o aberto a partir da sua vigência
    perfil = PerfilTributario(regime=dados["regime"], vigente_de=vigente_de, vigente_ate=vigente_ate, tipo_receita=tipo,
                              municipio=municipio, componentes=componentes, aliquota_efetiva=efetiva,
                              metodo_calculo=dados.get("metodo_calculo") or "SOBRE_RECEITA_RECEBIDA", fonte=dados.get("fonte"),
                              observacoes=dados.get("observacoes"), criado_por=ator_id)
    db.add(perfil)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "perfil_tributario_criado", "perfil_tributario", perfil.id,
                                ator_id, {"dados": {**{k: str(v) for k, v in dados.items() if k != "componentes"},
                                                    "componentes": componentes, "aliquota_efetiva": efetiva}, "origem": "admin"})
    return perfil


def como_dict(perfil: PerfilTributario) -> dict:
    return {"id": perfil.id, "regime": perfil.regime, "vigente_de": perfil.vigente_de.isoformat(),
            "vigente_ate": perfil.vigente_ate.isoformat() if perfil.vigente_ate else None, "tipo_receita": perfil.tipo_receita,
            "municipio": perfil.municipio, "componentes": perfil.componentes, "aliquota_efetiva": perfil.aliquota_efetiva,
            "metodo_calculo": perfil.metodo_calculo, "fonte": perfil.fonte, "observacoes": perfil.observacoes}
