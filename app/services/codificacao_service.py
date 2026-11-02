"""Acha e corrige nomes de empresas e contatos já gravados com a codificação trocada ("QuÃ©bec" no lugar de "Québec").

A gravação nova já é corrigida por `app/models/codificacao.py`; este serviço trata o que ficou gravado antes. Sem `aplicar`, só conta e mostra exemplos (simulação).
"""

from sqlalchemy.orm import Session

from app.core.texto import corrigir_codificacao
from app.models.codificacao import CAMPOS_CORRIGIDOS
from app.services import auditoria_service

_EXEMPLOS_POR_MODELO = 10


def corrigir_dados_gravados(db: Session, *, aplicar: bool = False) -> dict:
    """Varre os campos de `CAMPOS_CORRIGIDOS` de todos os tenants. Devolve, por modelo, quantos registros e campos estão com a troca e alguns exemplos (antes e
    depois). Só os nomes de EMPRESA entram nos exemplos: o nome e o cargo de uma pessoa são dado pessoal e aparecem apenas na contagem. Com `aplicar`, grava as
    correções e registra um evento de auditoria por tenant; sem `aplicar`, nada é alterado."""
    relatorio: dict[str, dict] = {}
    por_tenant: dict[str, dict[str, int]] = {}
    for modelo, campos in CAMPOS_CORRIGIDOS.items():
        registros = 0
        campos_alterados = 0
        exemplos: list[dict] = []
        for objeto in db.query(modelo).yield_per(500):
            mudou = False
            for campo in campos:
                valor = getattr(objeto, campo)
                corrigido = corrigir_codificacao(valor) if isinstance(valor, str) else valor
                if corrigido == valor:
                    continue
                mudou = True
                campos_alterados += 1
                if modelo.__name__ == "Conta" and campo == "nome" and len(exemplos) < _EXEMPLOS_POR_MODELO:
                    exemplos.append({"antes": valor, "depois": corrigido})
                if aplicar:
                    setattr(objeto, campo, corrigido)
            if mudou:
                registros += 1
                contagem = por_tenant.setdefault(objeto.tenant_id, {})
                contagem[modelo.__name__] = contagem.get(modelo.__name__, 0) + 1
        relatorio[modelo.__name__] = {"registros": registros, "campos": campos_alterados, "exemplos": exemplos}

    if aplicar:
        for tenant_id, contagem in por_tenant.items():
            auditoria_service.registrar(db, tenant_id, "codificacao_corrigida", "tenant", 0, None, contagem)
        db.commit()
    relatorio["aplicado"] = aplicar
    relatorio["tenants_afetados"] = len(por_tenant)
    return relatorio
