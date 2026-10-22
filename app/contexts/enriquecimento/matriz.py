"""Aplicação da matriz comercial de enriquecimento (franquias por plano) sobre os planos que existem no banco.

Idempotente e versionada: um plano cuja configuração aprovada já bate com a matriz não ganha versão nova; um que difere ganha uma versão nova, já
aprovada em nome do PO (a matriz é decisão do PO), com o histórico anterior preservado. Plano que não existe no banco NÃO é criado (criar plano exigiria
preço, que a matriz não define): aparece no relatório e a matriz vale quando ele existir (rodar de novo). Enterprise é configurado por administrador,
por tenant, e não recebe linha de plano.

Casamento matriz → plano: por nome exato (ou apelido listado em `matriz_dados`). Nada é adivinhado: no banco os planos de produto se chamam "PREDATOR
Starter", "PREDATOR Professional" etc., e ligar "Starter" a um deles é decisão comercial, tomada pelo administrador com `mapeamento` ({linha da
matriz: id do plano}). Sem mapeamento e sem nome exato, a linha fica em `nao_encontrados`."""

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config
from app.contexts.enriquecimento.matriz_dados import APROVADOR_MATRIZ, MOTIVO_MATRIZ, PLANOS
from app.models.enriquecimento_creditos import EnriquecimentoConfigPlano
from app.models.plano import Plano
from app.services.errors import NaoEncontrado

_CAMPOS = config.CAMPOS_NUMERICOS + ("periodicidade", "modo")


def _planos_existentes(db: Session, chave: str, aliases: tuple[str, ...], mapeamento: dict[str, int] | None) -> list[Plano]:
    """Todos os planos do banco que pertencem à linha da matriz: o mapeamento explícito, ou cada nome/apelido existente (ex.: "Starter" da suíte e
    "PREDATOR Starter" do módulo avulso, que têm a mesma franquia de pesquisa de decisores)."""
    if mapeamento and chave in mapeamento:
        plano = db.get(Plano, mapeamento[chave])
        if plano is None:
            raise NaoEncontrado(f"Plano {mapeamento[chave]} (linha {chave} da matriz) não existe.")
        return [plano]
    return db.query(Plano).filter(Plano.nome.in_(aliases)).order_by(Plano.id).all()


def _valores(linha: EnriquecimentoConfigPlano) -> dict:
    return {campo: getattr(linha, campo) for campo in _CAMPOS}


def aplicar(db: Session, *, ator_id: str | None, tenant_auditoria: str, mapeamento: dict[str, int] | None = None) -> dict:
    """Aplica a matriz aos planos existentes. Devolve o relatório: aplicados, inalterados, não encontrados e os que são por administrador."""
    relatorio: dict[str, list] = {"aplicados": [], "inalterados": [], "nao_encontrados": [], "por_administrador": [], "ajustes": []}
    for chave, spec in PLANOS.items():
        planos = _planos_existentes(db, chave, spec["aliases"], mapeamento)
        if not planos:
            relatorio["nao_encontrados"].append(chave)
            continue
        for plano in planos:
            _aplicar_ao_plano(db, plano, spec, ator_id, tenant_auditoria, relatorio)
    return relatorio


def _aplicar_ao_plano(db: Session, plano: Plano, spec: dict, ator_id: str | None, tenant_auditoria: str, relatorio: dict) -> None:
    if spec["config"] is None:
        relatorio["por_administrador"].append(plano.nome)
        return
    atual = config.config_aprovada_do_plano(db, plano.id)
    base = _valores(atual) if atual is not None else {campo: None for campo in _CAMPOS}
    alvo = {**base, **{campo: valor for campo, valor in spec["config"].items()}}
    padrao, maximo = alvo.get("decisores_por_empresa_padrao"), alvo.get("decisores_por_empresa_max")
    if padrao is not None and maximo is not None and padrao > maximo:
        # Configuração anterior que permitia mais decisores do que a matriz (ex.: padrão de 5 no Teste gratuito): o padrão é removido, nunca o
        # teto da matriz relaxado. O usuário passa a escolher o número de decisores (até o teto).
        alvo["decisores_por_empresa_padrao"] = None
        relatorio["ajustes"].append({"plano": plano.nome, "campo": "decisores_por_empresa_padrao", "de": padrao, "para": None})
    if atual is not None and _valores(atual) == alvo:
        relatorio["inalterados"].append(plano.nome)
        return
    nova = config.definir_config(db, plano_id=plano.id, tenant_id=None, campos=alvo, ator_id=APROVADOR_MATRIZ, tenant_auditoria=tenant_auditoria,
                                 motivo=f"{MOTIVO_MATRIZ} (aplicada por {ator_id or 'sistema'})", aprovar=True)
    relatorio["aplicados"].append({"plano": plano.nome, "versao": nova.versao})


def status(db: Session, mapeamento: dict[str, int] | None = None) -> list[dict]:
    """Para cada linha da matriz: o plano existe no banco? A configuração aprovada bate com a matriz?"""
    saida = []
    for chave, spec in PLANOS.items():
        planos = _planos_existentes(db, chave, spec["aliases"], mapeamento)
        if not planos:
            saida.append({"matriz": chave, "plano": None, "situacao": "plano_inexistente"})
        for plano in planos:
            if spec["config"] is None:
                saida.append({"matriz": chave, "plano": plano.nome, "situacao": "configuravel_por_administrador"})
                continue
            atual = config.config_aprovada_do_plano(db, plano.id)
            if atual is None:
                situacao = "nao_aplicada"
            else:
                valores = _valores(atual)
                situacao = "aplicada" if all(valores[c] == v for c, v in spec["config"].items()) else "diverge_da_matriz"
            saida.append({"matriz": chave, "plano": plano.nome, "situacao": situacao})
    return saida


def vitrine() -> list[dict]:
    """A matriz como o site e a plataforma a apresentam (sem banco): franquia mensal, limite de créditos por pesquisa e de decisores por empresa por
    linha comercial. É a tabela aprovada pelo PO; não inclui mensalidade (a matriz não define preço de plano). Enterprise e POC são condições
    negociadas/autorizadas, não franquias fixas."""
    saida = []
    for chave, spec in PLANOS.items():
        cfg = spec["config"]
        if cfg is None:
            saida.append({"plano": chave, "modo": "sob_consulta", "descricao": "Limites de contatos, créditos, empresas e operações por período definidos sob medida com o comercial."})
        elif cfg["modo"] == "poc_autorizada":
            saida.append({"plano": chave, "modo": "poc_autorizada", "decisores_por_empresa_max": cfg["decisores_por_empresa_max"],
                          "descricao": "Sem franquia fixa: cada operação é autorizada com orçamento calculado pelas tarifas confirmadas."})
        else:
            saida.append({"plano": chave, "modo": "franquia_fixa", "franquia_creditos": cfg["franquia_creditos"], "periodicidade": cfg["periodicidade"],
                          "limite_creditos_pesquisa": cfg["limite_creditos_pesquisa"], "decisores_por_empresa_max": cfg["decisores_por_empresa_max"]})
    return saida
