"""Commission Policy da Margem Comissionável Líquida (D-075), versionada na tabela `politica_comissao`.

Impostos e infraestrutura atribuíveis são sempre deduzidos (D-074). O custo de IA só é deduzido quando a política diz
explicitamente (`deduzir_custo_ia`); a versão inicial não deduz. Mudar a política cria uma versão nova, auditada, que vale
para apurações novas e para o recálculo explícito das não pagas.
"""

from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import CODIGO_POLITICA_MARGEM, POLITICA_MARGEM_INICIAL
from app.models.contrato_governo import PoliticaComissao
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou


def vigente(db: Session) -> PoliticaComissao:
    politica = (db.query(PoliticaComissao).filter_by(codigo=CODIGO_POLITICA_MARGEM, ativa=True)
                .order_by(PoliticaComissao.versao.desc()).first())
    if politica is None:  # bancos criados sem a migração (testes, E2E)
        politica = PoliticaComissao(codigo=CODIGO_POLITICA_MARGEM, versao=1, regras=dict(POLITICA_MARGEM_INICIAL), ativa=True,
                                    motivo="Política inicial (D-075): custo de IA fora da margem", criado_por="semente")
        db.add(politica)
        db.flush()
    return politica


def nova(db: Session, regras: dict, motivo: str, ator_id: str | None) -> PoliticaComissao:
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da mudança de política.")
    if set(regras) != set(POLITICA_MARGEM_INICIAL) or not isinstance(regras.get("deduzir_custo_ia"), bool):
        raise ValidacaoFalhou("A política da margem só define deduzir_custo_ia (true/false); impostos e infraestrutura são sempre deduzidos.")
    anterior = vigente(db)
    anterior.ativa = False
    politica = PoliticaComissao(codigo=CODIGO_POLITICA_MARGEM, versao=anterior.versao + 1, regras=regras, ativa=True, motivo=motivo,
                                criado_por=ator_id)
    db.add(politica)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "politica_comissao_alterada", "politica_comissao", politica.id,
                                ator_id, {"codigo": CODIGO_POLITICA_MARGEM, "antes": anterior.regras, "depois": regras,
                                          "versao": politica.versao, "motivo": motivo, "origem": "admin"})
    return politica
