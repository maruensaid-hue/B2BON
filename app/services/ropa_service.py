from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.registro_tratamento import RegistroTratamento
from app.schemas.registro_tratamento import RegistroTratamentoCreateSchema
from app.services import auditoria_service
from app.services.auditoria_service import TENANT_PLATAFORMA

# Colunas técnicas/estruturais — não são "dados coletados" para fins de
# minimização (chaves, FKs e carimbos de tempo de auditoria).
_COLUNAS_TECNICAS = {"id", "tenant_id", "conta_id", "icp_id", "neo4j_node_id", "criado_em", "atualizado_em"}


def _colunas_de_dados(modelo) -> set[str]:
    return {coluna.key for coluna in inspect(modelo).columns} - _COLUNAS_TECNICAS


def listar_ativos_plataforma(db: Session) -> list[RegistroTratamento]:
    return db.query(RegistroTratamento).filter_by(ativo=True).all()


def criar_versao_plataforma(
    db: Session, ator_id: str | None, dados: RegistroTratamentoCreateSchema
) -> RegistroTratamento:
    """ROPA de plataforma, versionado — operações padrão do módulo,
    plataforma como operadora (E9-H1)."""
    anterior = (
        db.query(RegistroTratamento)
        .filter_by(tipo_tratamento=dados.tipo_tratamento, ativo=True)
        .one_or_none()
    )
    versao = (anterior.versao + 1) if anterior else 1
    if anterior:
        anterior.ativo = False

    registro = RegistroTratamento(
        tipo_tratamento=dados.tipo_tratamento,
        finalidade=dados.finalidade,
        dados_tratados=dados.dados_tratados,
        balanceamento_documentado=dados.balanceamento_documentado,
        versao=versao,
        ativo=True,
    )
    db.add(registro)
    db.flush()

    auditoria_service.registrar(
        db,
        TENANT_PLATAFORMA,
        "ropa_plataforma_registrado",
        "registro_tratamento",
        registro.id,
        ator_id,
        {"tipo_tratamento": registro.tipo_tratamento, "versao": registro.versao},
    )
    db.commit()
    db.refresh(registro)
    return registro


def _tem_decisores(db: Session, tenant_id: str) -> bool:
    return (
        db.query(Decisor)
        .join(Conta, Decisor.conta_id == Conta.id)
        .filter(Conta.tenant_id == tenant_id)
        .first()
        is not None
    )


def gerar_ropa_tenant(db: Session, tenant_id: str) -> dict:
    """ROPA por tenant, gerado automaticamente da configuração do assinante
    (canais ativos, fontes de dados, ICP) — o assinante é o controlador dos
    dados de prospecção (E9-H1). Computado sob demanda, nunca fica
    desatualizado."""
    icps_ativos = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).all()

    fontes_origem = {
        origem for (origem,) in db.query(Conta.origem).filter_by(tenant_id=tenant_id).all() if origem
    }
    fontes_enriquecimento = {
        fonte
        for (fonte,) in db.query(CampoEnriquecido.fonte)
        .join(Conta, CampoEnriquecido.conta_id == Conta.id)
        .filter(Conta.tenant_id == tenant_id)
        .all()
    }
    fontes_dados = sorted(fontes_origem | fontes_enriquecimento)

    canais_ativos: set[str] = set()
    for (canais,) in db.query(Cadencia.canais).filter_by(tenant_id=tenant_id).all():
        canais_ativos.update(canais or [])

    dados_tratados = sorted(
        _colunas_de_dados(Conta) | (_colunas_de_dados(Decisor) if _tem_decisores(db, tenant_id) else set())
    )

    return {
        "tenant_id": tenant_id,
        "icp_ids": [icp.id for icp in icps_ativos],
        "fontes_dados": fontes_dados,
        "canais_ativos": sorted(canais_ativos),
        "dados_tratados": dados_tratados,
        "base_legal": "legitimo_interesse",
    }


def verificar_minimizacao(db: Session, tenant_id: str) -> dict:
    """Motor não coleta dados além do necessário ao ICP (E9-H1): confere se
    as colunas de dados realmente persistidas em Conta/Decisor estão todas
    declaradas em algum ROPA (plataforma ativo ou do tenant).

    Colunas de Decisor só entram na checagem se o tenant já tiver decisores
    mapeados — sem isso, nada foi de fato coletado naquele espaço.
    """
    declarados: set[str] = set()
    for registro in listar_ativos_plataforma(db):
        declarados.update(registro.dados_tratados)
    declarados.update(gerar_ropa_tenant(db, tenant_id)["dados_tratados"])

    colunas_reais = _colunas_de_dados(Conta) | (
        _colunas_de_dados(Decisor) if _tem_decisores(db, tenant_id) else set()
    )
    divergencias = sorted(colunas_reais - declarados)
    return {"conforme": not divergencias, "divergencias": divergencias}
