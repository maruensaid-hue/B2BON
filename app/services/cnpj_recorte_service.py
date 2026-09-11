import tempfile
from pathlib import Path

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.icp import ICP
from app.models.recorte_cnpj_estado import RecorteCnpjEstado
from app.providers.account_data.receita_federal_downloader import (
    baixar_shards,
    normalizar_cnae,
    resolver_mes_competencia,
)
from app.providers.account_data.receita_federal_loader import carregar_recorte
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento

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
    por um passo 100% automático: calcula os CNAE/UF exigidos por todos os
    ICPs ativos de todos os tenants, baixa da própria Receita Federal só o
    que ainda não foi coberto, e recarrega o staging local
    (`cnpj_estabelecimento`). Nenhuma intervenção humana — nem escolha de
    caminho de arquivo, nem execução manual de script.

    Chamada por `scripts/carregar_recorte_ci.py`, sempre num runner do
    GitHub Actions (workflow_dispatch manual ou agendado a cada 30 min em
    `cron-envios.yml`) — nunca por um endpoint do Render (raio-X
    2026-09-09: já existiu um `POST /cron/atualizar-recorte-cnpj`, removido
    depois de estourar a cota fixa de 2GB do `/tmp` do Render durante o
    download de um ICP novo).

    Idempotente por natureza (`carregar_recorte` faz upsert por CNPJ), mas
    evita trabalho redundante: só baixa de novo quando há CNAE/UF novo
    desde a última carga ou quando a Receita Federal publicou um mês de
    competência mais recente."""
    cnae_codigos, ufs = uniao_cnae_uf_ativos_todos_tenants(db)
    if not cnae_codigos or not ufs:
        return {"executado": False, "motivo": "nenhum ICP ativo em nenhum tenant"}

    estado = _obter_ou_criar_estado(db)
    # Fecha a transação aqui, antes do download (que sozinho já passa de
    # alguns minutos sem tráfego nenhum no banco) — sem isso, a transação
    # aberta desde a leitura acima fica "idle in transaction" o tempo
    # inteiro do download, e o Neon mata a conexão por conta disso antes
    # mesmo da varredura do CSV começar (raio-X 2026-08-27).
    db.commit()
    mes_competencia = resolver_mes_competencia()

    ja_coberto = (
        estado.mes_competencia == mes_competencia
        and set(cnae_codigos) <= set(estado.cnae_codigos_cobertos)
        and set(ufs) <= set(estado.ufs_cobertos)
    )
    if ja_coberto:
        return {"executado": False, "motivo": "recorte já cobre todos os ICPs ativos neste mês de competência"}

    cnae_antigos = set(estado.cnae_codigos_cobertos)
    ufs_antigos = set(estado.ufs_cobertos)
    mudou_mes = estado.mes_competencia != mes_competencia

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
            # Mesmo mês de competência: só o que ainda não estava coberto
            # precisa ser gravado de novo — evita reescrever no banco
            # milhões de linhas que já estavam corretas no staging só
            # porque um ICP com CNAE/UF novo foi criado (raio-X
            # 2026-09-11: um ICP novo obrigava reescrever TODO o recorte
            # de TODOS os ICPs ativos, não só o dele). Mês novo publicado
            # pela Receita Federal é diferente: dados de qualquer empresa
            # já coberta podem ter mudado, não só das combinações novas —
            # aí sim regrava tudo (`None` = sem exclusão, igual antes).
            cnae_ja_cobertos=None if mudou_mes else cnae_antigos,
            ufs_ja_cobertos=None if mudou_mes else ufs_antigos,
        )

    estado.mes_competencia = mes_competencia
    estado.cnae_codigos_cobertos = sorted(cnae_antigos | set(cnae_codigos))
    estado.ufs_cobertos = sorted(ufs_antigos | set(ufs))
    db.commit()

    return {
        "executado": True,
        "mes_competencia": mes_competencia,
        "estabelecimentos_carregados": carregados,
        "cnae_codigos_cobertos": estado.cnae_codigos_cobertos,
        "ufs_cobertos": estado.ufs_cobertos,
    }


def podar_recorte_nao_utilizado(db: Session) -> dict:
    """Remove do staging local (`cnpj_estabelecimento`/`cnpj_socio`) tudo
    que não é mais exigido por nenhum ICP ativo de nenhum tenant —
    recupera espaço de CNAE/UF que ficaram cobertos no passado (ICP
    desativado ou substituído por uma nova versão) mas não são usados por
    ninguém hoje (raio-X 2026-09-11: sem isso, o staging só cresce pra
    sempre e pode estourar a cota de armazenamento do banco — foi
    exatamente o que aconteceu quando um ICP novo com CNAE amplo foi
    criado).

    Deliberadamente **não** roda automaticamente a cada carga — só quando
    chamada explicitamente (cron 1x/dia) — porque é uma operação de
    exclusão, ao contrário da carga (que só soma)."""
    cnae_ativos, ufs_ativos = uniao_cnae_uf_ativos_todos_tenants(db)
    cnae_set = set(cnae_ativos)
    uf_set = {uf.upper() for uf in ufs_ativos}
    if not cnae_set or not uf_set:
        # Nenhum ICP ativo em tenant nenhum — provavelmente uma falha
        # transitória lendo os ICPs, não o estado real do produto. Apagar
        # tudo por conta disso seria destrutivo demais pra um caso que
        # deveria ser raríssimo; melhor não podar nada do que podar errado.
        return {"executado": False, "motivo": "nenhum ICP ativo em nenhum tenant — nada podado por segurança"}

    fora_do_recorte = or_(
        ~CnpjEstabelecimento.cnae_principal.in_(cnae_set), ~CnpjEstabelecimento.uf.in_(uf_set)
    )
    estabelecimentos_removidos = (
        db.query(CnpjEstabelecimento).filter(fora_do_recorte).delete(synchronize_session=False)
    )
    db.commit()

    # Sócios cujo cnpj_basico não tem mais nenhum estabelecimento no
    # staging (nem o que acabou de ser removido, nem nenhum antigo já
    # órfão) — via SQL direto porque `CnpjSocio` só guarda o cnpj_basico
    # (8 dígitos), não a chave completa, e comparar prefixo em lote pelo
    # ORM custaria uma consulta por lote de CNPJs em vez de uma só.
    socios_removidos = db.execute(
        text(
            "DELETE FROM cnpj_socio WHERE cnpj_basico NOT IN ("
            "SELECT DISTINCT substr(cnpj, 1, 8) FROM cnpj_estabelecimento"
            ")"
        )
    ).rowcount
    db.commit()

    # Encolhe o estado de cobertura pra bater com o que sobrou de fato —
    # senão, quando um CNAE/UF podado voltar a ser necessário (ICP
    # reativado), o sistema acharia que "já está coberto" e nunca
    # rebaixaria os dados de volta.
    estado = _obter_ou_criar_estado(db)
    estado.cnae_codigos_cobertos = sorted(cnae_set)
    estado.ufs_cobertos = sorted(uf_set)
    db.commit()

    return {
        "executado": True,
        "estabelecimentos_removidos": estabelecimentos_removidos,
        "socios_removidos": socios_removidos,
        "cnae_codigos_cobertos": estado.cnae_codigos_cobertos,
        "ufs_cobertos": estado.ufs_cobertos,
    }
