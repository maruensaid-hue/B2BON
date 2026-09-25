"""Validação estrutural do modelo canônico (Fase 2)."""

import json

import pytest
from pydantic import ValidationError

from app.contexts.shared.canonical.base import DataClassification, DataOrigin, SourceRef, canonical_id
from app.contexts.shared.canonical.commercial import COMMERCIAL_ENTITIES, Organization
from app.contexts.shared.canonical.procurement import PROCUREMENT_ENTITIES, BidOpportunity, Demand

FONTE = SourceRef(system="teste", external_id="1", entity="x")


def test_modelo_comercial_cobre_as_21_entidades_do_master_prompt():
    nomes = {entidade.__name__ for entidade in COMMERCIAL_ENTITIES}
    assert nomes == {
        "Organization", "Person", "Lead", "Account", "Contact", "Opportunity", "Pipeline", "PipelineStage",
        "Activity", "Meeting", "Message", "Product", "Offer", "Proposal", "Contract", "Customer", "Revenue",
        "Invoice", "Interaction", "CSMetric", "BusinessIntent",
    }


def test_modelo_de_procurement_cobre_as_20_entidades_do_master_prompt():
    nomes = {entidade.__name__ for entidade in PROCUREMENT_ENTITIES}
    assert nomes == {
        "PublicOrganization", "ProcurementUnit", "ProcurementUser", "Demand", "ProcurementPlan", "PCAItem",
        "ProcurementProcess", "ProcurementDocument", "ProcurementLot", "ProcurementItem", "Supplier",
        "SupplierPerformance", "PriceResearch", "BudgetAllocation", "PublicContract", "Deliverable",
        "Inspection", "Amendment", "ProcurementRisk", "BidOpportunity",
    }


@pytest.mark.parametrize("entidade", COMMERCIAL_ENTITIES + PROCUREMENT_ENTITIES, ids=lambda e: e.__name__)
def test_toda_entidade_gera_json_schema_com_proveniencia_e_classificacao(entidade):
    schema = entidade.model_json_schema()
    json.dumps(schema)
    for campo in ("id", "tenant_id", "source", "origin", "classification"):
        assert campo in schema["properties"], (entidade.__name__, campo)


def test_default_de_classificacao_nunca_e_publico():
    org = Organization(id="a", tenant_id="t", source=FONTE, legal_name="X")
    assert org.classification == DataClassification.INTERNAL
    assert org.origin == DataOrigin.INTERNAL


def test_dado_interno_do_comprador_nasce_confidencial():
    demanda = Demand(id="d", tenant_id="t", source=FONTE, requesting_unit_id="u", business_need="n", status="aberta")
    assert demanda.classification == DataClassification.CONFIDENTIAL


def test_edital_publicado_pode_ser_marcado_publico_explicitamente():
    bid = BidOpportunity(
        id="b", tenant_id="t", source=FONTE, issuer_name="Órgão", kind="PUBLIC_TENDER", object="obj",
        status="aberta", classification=DataClassification.PUBLIC,
    )
    assert bid.classification == DataClassification.PUBLIC


def test_campo_desconhecido_e_rejeitado_e_objeto_e_imutavel():
    with pytest.raises(ValidationError):
        Organization(id="a", tenant_id="t", source=FONTE, legal_name="X", campo_inventado=1)
    org = Organization(id="a", tenant_id="t", source=FONTE, legal_name="X")
    with pytest.raises(ValidationError):
        org.legal_name = "Y"


def test_id_canonico_e_estavel_e_nao_colide_entre_sistemas():
    assert canonical_id("b2bon_crm", "account", 7) == canonical_id("b2bon_crm", "account", "7")
    assert canonical_id("b2bon_crm", "account", 7) != canonical_id("hubspot", "account", 7)
