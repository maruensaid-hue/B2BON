"""Competitive Intelligence (Fase 9): histórico do próprio tenant contra
cada concorrente, só com dado registrado (concorrentes informados e
vencedor das licitações encerradas). Sem dado de mercado inventado."""

from sqlalchemy.orm import Session

from app.contexts.shared.texto import normalizar
from app.models.licitacao import Licitacao


def resumo(db: Session, tenant_id: str) -> list[dict]:
    por_concorrente: dict[str, dict] = {}
    for lic in db.query(Licitacao).filter_by(tenant_id=tenant_id).all():
        for nome in lic.concorrentes or []:
            chave = normalizar(nome)
            if not chave:
                continue
            item = por_concorrente.setdefault(chave, {"concorrente": nome, "disputas": 0, "ganhamos": 0, "eles_ganharam": 0,
                                                      "outros_ganharam": 0, "em_aberto": 0, "licitacoes": []})
            item["disputas"] += 1
            item["licitacoes"].append(lic.id)
            if lic.status == "GANHA":
                item["ganhamos"] += 1
            elif lic.status == "PERDIDA":
                if lic.vencedor and normalizar(lic.vencedor) == chave:
                    item["eles_ganharam"] += 1
                else:
                    item["outros_ganharam"] += 1
            else:
                item["em_aberto"] += 1
    for item in por_concorrente.values():
        decididas = item["ganhamos"] + item["eles_ganharam"] + item["outros_ganharam"]
        item["taxa_vitoria_contra"] = round(item["ganhamos"] / decididas, 2) if decididas else None
    return sorted(por_concorrente.values(), key=lambda i: (-i["disputas"], i["concorrente"]))
