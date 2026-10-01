"""Políticas versionadas do Commission Engine, na tabela `politica_comissao`:

- `NET_COMMISSIONABLE_MARGIN` (D-075): impostos e infraestrutura atribuíveis são sempre deduzidos (D-074); o custo de IA
  só é deduzido quando a política diz explicitamente (`deduzir_custo_ia`). A versão inicial não deduz.
- `INFRASTRUCTURE_COST_POLICY` (D-076): pesos de infraestrutura por tier, limiares de capacidade e a base de custo da
  comissão (inicialmente o custo PROVISIONADO, conservador).

Mudar uma política cria uma versão nova, auditada, que vale para apurações novas e para o recálculo explícito das não
pagas; comissões pagas não mudam.
"""

from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import (
    CODIGO_POLITICA_INFRA,
    CODIGO_POLITICA_MARGEM,
    POLITICA_INFRA_INICIAL,
    POLITICA_MARGEM_INICIAL,
    TIERS_INFRA,
)
from app.models.contrato_governo import PoliticaComissao
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

INICIAIS = {
    CODIGO_POLITICA_MARGEM: (POLITICA_MARGEM_INICIAL, "Política inicial (D-075): custo de IA fora da margem"),
    CODIGO_POLITICA_INFRA: (POLITICA_INFRA_INICIAL, "Política inicial do PO (D-076): plano máximo, pesos 1/1/2/4"),
}


def _vigente(db: Session, codigo: str) -> PoliticaComissao:
    politica = (db.query(PoliticaComissao).filter_by(codigo=codigo, ativa=True).order_by(PoliticaComissao.versao.desc()).first())
    if politica is None:  # bancos criados sem a migração (testes, E2E)
        regras, motivo = INICIAIS[codigo]
        politica = PoliticaComissao(codigo=codigo, versao=1, regras=dict(regras), ativa=True, motivo=motivo, criado_por="semente")
        db.add(politica)
        db.flush()
    return politica


def vigente(db: Session) -> PoliticaComissao:
    return _vigente(db, CODIGO_POLITICA_MARGEM)


def vigente_infra(db: Session) -> PoliticaComissao:
    return _vigente(db, CODIGO_POLITICA_INFRA)


def _validar_infra(regras: dict) -> None:
    pesos, limiares = regras.get("pesos") or {}, regras.get("limiares") or {}
    if not pesos or set(pesos) - set(TIERS_INFRA) or any(not isinstance(v, int | float) or v <= 0 for v in pesos.values()):
        raise ValidacaoFalhou(f"Pesos de infraestrutura positivos por tier ({', '.join(TIERS_INFRA)}).")
    ordem = ("ATTENTION", "REVIEW", "CRITICAL", "CAPACITY_REACHED")
    if set(limiares) != set(ordem):
        raise ValidacaoFalhou(f"Limiares de capacidade: {', '.join(ordem)}.")
    valores = [float(limiares[n]) for n in ordem]
    if any(v <= 0 for v in valores) or valores != sorted(valores) or len(set(valores)) != len(valores):
        raise ValidacaoFalhou("Limiares crescentes e positivos (ex.: 0,70 < 0,80 < 0,90 < 1,00).")
    if regras.get("custo_comissao") not in ("PROVISIONED", "ACTUAL"):
        raise ValidacaoFalhou("custo_comissao: PROVISIONED ou ACTUAL.")
    if set(regras) - {"pesos", "limiares", "custo_comissao"}:
        raise ValidacaoFalhou("A política de infraestrutura só define pesos, limiares e custo_comissao.")


def _validar_margem(regras: dict) -> None:
    if set(regras) != set(POLITICA_MARGEM_INICIAL) or not isinstance(regras.get("deduzir_custo_ia"), bool):
        raise ValidacaoFalhou("A política da margem só define deduzir_custo_ia (true/false); impostos e infraestrutura são sempre deduzidos.")


def _nova(db: Session, codigo: str, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da mudança de política.")
    (_validar_infra if codigo == CODIGO_POLITICA_INFRA else _validar_margem)(regras)
    anterior = _vigente(db, codigo)
    anterior.ativa = False
    politica = PoliticaComissao(codigo=codigo, versao=anterior.versao + 1, regras=regras, ativa=True, motivo=motivo, criado_por=ator_id)
    db.add(politica)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "politica_comissao_alterada", "politica_comissao", politica.id,
                                ator_id, {"codigo": codigo, "antes": anterior.regras, "depois": regras, "versao": politica.versao,
                                          "motivo": motivo, "origem": "admin"})
    return politica


def nova(db: Session, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    return _nova(db, CODIGO_POLITICA_MARGEM, regras, motivo, ator_id)


def nova_infra(db: Session, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    return _nova(db, CODIGO_POLITICA_INFRA, regras, motivo, ator_id)
