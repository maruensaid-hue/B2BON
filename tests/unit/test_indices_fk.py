"""Fitness function (Fase 17): toda chave estrangeira tem índice.

Exceção: colunas de autoria (quem criou/aprovou/revisou/enviou), que não
são usadas como filtro. Tabela nova com FK sem índice quebra este teste:
indexe a coluna no modelo (`index=True`) ou em `app/models/indices_fk.py`
com a migração correspondente.
"""

import re

import app.models  # noqa: F401 — carrega todos os modelos e os índices de FK
from app.db.base import Base
from app.models.indices_fk import INDICES_FK

AUTORIA = re.compile(
    r"^(criado_por|aprovado_por|revisado_por|enviado_por|decidido_por|usado_por|solicitante|aprovador|remetente|responsavel)_usuario_id$"
)


def _colunas_lideres(tabela) -> set[str]:
    lideres = {list(indice.columns)[0].name for indice in tabela.indexes}
    for restricao in tabela.constraints:
        colunas = list(getattr(restricao, "columns", []))
        if colunas and type(restricao).__name__ in ("PrimaryKeyConstraint", "UniqueConstraint"):
            lideres.add(colunas[0].name)
    return lideres


def test_toda_fk_tem_indice_exceto_autoria():
    sem_indice = []
    for tabela in Base.metadata.sorted_tables:
        lideres = _colunas_lideres(tabela)
        for coluna in tabela.columns:
            if coluna.foreign_keys and coluna.name not in lideres and not coluna.index and not AUTORIA.search(coluna.name):
                sem_indice.append(f"{tabela.name}.{coluna.name}")
    assert sem_indice == [], sem_indice


def test_lista_de_indices_so_tem_fk_existente():
    for tabela, coluna in INDICES_FK:
        assert Base.metadata.tables[tabela].c[coluna].foreign_keys, f"{tabela}.{coluna} não é FK"
