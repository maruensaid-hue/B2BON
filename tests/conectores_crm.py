"""Suíte de conformidade compartilhada pelos conectores de CRM (Fase 13).

Todo conector passa pelas mesmas verificações de contrato, além dos
testes de mapeamento próprios: tenant forçado, proveniência, ids
canônicos do sistema, paginação até o fim, referências consistentes e
isolamento (outro tenant não enxerga nada).
"""

from app.contexts.integrations.contract import CrmAdapter, iterar_todos

_PAGINADAS = ("list_organizations", "list_accounts", "list_customers", "list_people", "list_contacts",
              "list_opportunities", "list_activities", "list_interactions", "list_cs_metrics")


def coletar(adapter: CrmAdapter, tenant_id: str) -> dict[str, list]:
    dados = {nome.removeprefix("list_"): iterar_todos(getattr(adapter, nome), tenant_id) for nome in _PAGINADAS}
    dados["pipelines"] = adapter.list_pipelines(tenant_id)
    dados["stages"] = adapter.list_stages(tenant_id)
    dados["offers"] = adapter.list_offers(tenant_id)
    return dados


def verificar_contrato(adapter: CrmAdapter, tenant_id: str, sistema: str) -> dict[str, list]:
    capacidades = adapter.capabilities()
    assert capacidades.system == sistema
    assert not capacidades.writable_entities, "conectores da Fase 13 são somente leitura"
    dados = coletar(adapter, tenant_id)
    for entidade, itens in dados.items():
        for item in itens:
            assert item.tenant_id == tenant_id, entidade
            assert item.source.system == sistema and item.source.external_id, entidade
            assert item.id.startswith(f"{sistema}:"), (entidade, item.id)
        if itens:
            assert entidade in capacidades.readable_entities, f"{entidade} devolvido mas não declarado"
        ids = [i.id for i in itens]
        assert len(ids) == len(set(ids)), f"ids duplicados em {entidade}"

    contas = {a.id for a in dados["accounts"]}
    organizacoes = {o.id for o in dados["organizations"]}
    estagios = {s.id for s in dados["stages"]}
    pipelines = {p.id for p in dados["pipelines"]}
    assert all(a.organization_id in organizacoes for a in dados["accounts"])
    assert all(o.account_id in contas and o.pipeline_id in pipelines for o in dados["opportunities"])
    assert all(o.stage_id in estagios for o in dados["opportunities"]), "oportunidade em estágio desconhecido"
    assert all(s.pipeline_id in pipelines for s in dados["stages"])
    assert all(c.account_id in contas for c in dados["customers"] + dados["contacts"] + dados["interactions"])

    outro = coletar(adapter, "tenant-que-nao-e-dono-da-conexao")
    assert not any(outro.values()), "adapter devolveu dados para outro tenant"
    return dados
