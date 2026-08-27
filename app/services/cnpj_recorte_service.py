import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.icp import ICP
from app.models.recorte_cnpj_estado import RecorteCnpjEstado
from app.providers.account_data.receita_federal_downloader import (
    baixar_shards,
    normalizar_cnae,
    resolver_mes_competencia,
)
from app.providers.account_data.receita_federal_loader import carregar_recorte

_ID_ESTADO = 1


def uniao_cnae_uf_ativos_todos_tenants(db: Session) -> tuple[list[str], list[str]]:
    """Igual a `scripts.carregar_recorte_receita_federal._unir_filtros_icps_ativos`,
    mas sem filtrar por tenant — o recorte automático via cron precisa
    cobrir os ICPs ativos de TODOS os tenants numa carga só (Onda de
    automação: elimina o passo manual por tenant)."""
    cnae_codigos: set[str] = set()
    ufs: set[str] = set()
    for icp in db.query(ICP).filter_by(ativo=True).all():
        cnae_codigos.update(normalizar_cnae(codigo) for codigo in icp.cnae_codigos)
        ufs.update(icp.ufs)
    return sorted(cnae_codigos), sorted(ufs)


def _obter_ou_criar_estado(db: Session) -> RecorteCnpjEstado:
    estado = db.query(RecorteCnpjEstado).filter_by(id=_ID_ESTADO).one_or_none()
    if estado is None:
        estado = RecorteCnpjEstado(id=_ID_ESTADO, mes_competencia="", cnae_codigos_cobertos=[], ufs_cobertos=[])
        db.add(estado)
        db.flush()
    return estado


def atualizar_recorte_automatico(db: Session) -> dict:
    """Substitui o script manual (`scripts/carregar_recorte_receita_federal.py`)
    por um passo 100% automático, pensado pra rodar via cron (mesmo padrão
    de `app/api/v1/cron.py`): calcula os CNAE/UF exigidos por todos os
    ICPs ativos de todos os tenants, baixa da própria Receita Federal só o
    que ainda não foi coberto, e recarrega o staging local
    (`cnpj_estabelecimento`). Nenhuma intervenção humana — nem escolha de
    caminho de arquivo, nem execução manual de script.

    Idempotente por natureza (`carregar_recorte` faz upsert por CNPJ), mas
    evita reduzir trabalho: só baixa de novo quando há CNAE/UF novo desde
    a última carga ou quando a Receita Federal publicou um mês de
    competência mais recente."""
    cnae_codigos, ufs = uniao_cnae_uf_ativos_todos_tenants(db)
    if not cnae_codigos or not ufs:
        return {"executado": False, "motivo": "nenhum ICP ativo em nenhum tenant"}

    estado = _obter_ou_criar_estado(db)
    mes_competencia = resolver_mes_competencia()

    ja_coberto = (
        estado.mes_competencia == mes_competencia
        and set(cnae_codigos) <= set(estado.cnae_codigos_cobertos)
        and set(ufs) <= set(estado.ufs_cobertos)
    )
    if ja_coberto:
        return {"executado": False, "motivo": "recorte já cobre todos os ICPs ativos neste mês de competência"}

    with tempfile.TemporaryDirectory(prefix="recorte_cnpj_") as diretorio_str:
        diretorio = Path(diretorio_str)
        caminhos_empresas = baixar_shards(mes_competencia, "Empresas", diretorio)
        caminhos_estabelecimentos = baixar_shards(mes_competencia, "Estabelecimentos", diretorio)
        caminhos_socios = baixar_shards(mes_competencia, "Socios", diretorio)

        carregados = carregar_recorte(
            db,
            cnae_codigos=cnae_codigos,
            ufs=ufs,
            caminho_empresas=caminhos_empresas,
            caminho_estabelecimentos=caminhos_estabelecimentos,
            caminho_socios=caminhos_socios,
        )

    estado.mes_competencia = mes_competencia
    estado.cnae_codigos_cobertos = sorted(set(estado.cnae_codigos_cobertos) | set(cnae_codigos))
    estado.ufs_cobertos = sorted(set(estado.ufs_cobertos) | set(ufs))
    db.commit()

    return {
        "executado": True,
        "mes_competencia": mes_competencia,
        "estabelecimentos_carregados": carregados,
        "cnae_codigos_cobertos": estado.cnae_codigos_cobertos,
        "ufs_cobertos": estado.ufs_cobertos,
    }
