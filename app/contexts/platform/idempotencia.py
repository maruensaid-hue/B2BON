"""Idempotência de escrita na API externa (Fase 3).

Uso no endpoint:
    anterior = idempotencia.buscar(db, tenant_id, chave, rota, corpo)
    if anterior: return anterior
    ... executa ...
    idempotencia.gravar(db, tenant_id, chave, rota, corpo, 201, resposta)

A mesma `Idempotency-Key` com corpo diferente é conflito (409), para um
cliente que reaproveita chave por engano não receber a resposta errada.
"""

import hashlib
import json

from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.registro_idempotencia import RegistroIdempotencia
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou


def _hash_corpo(corpo: dict) -> str:
    return hashlib.sha256(json.dumps(jsonable_encoder(corpo), sort_keys=True).encode()).hexdigest()


def validar_chave(chave: str | None) -> str:
    if not chave or not (8 <= len(chave) <= 128):
        raise ValidacaoFalhou("Header Idempotency-Key é obrigatório nesta operação (8 a 128 caracteres).")
    return chave


def buscar(db: Session, tenant_id: str, chave: str, rota: str, corpo: dict) -> RegistroIdempotencia | None:
    registro = db.query(RegistroIdempotencia).filter_by(tenant_id=tenant_id, chave=chave).one_or_none()
    if registro is None:
        return None
    if registro.rota != rota or registro.hash_corpo != _hash_corpo(corpo):
        raise RegraNegocioViolada("Idempotency-Key já usada com outra requisição. Gere uma chave nova.")
    return registro


def gravar(db: Session, tenant_id: str, chave: str, rota: str, corpo: dict, status_code: int, resposta) -> None:
    db.add(
        RegistroIdempotencia(
            tenant_id=tenant_id, chave=chave, rota=rota, hash_corpo=_hash_corpo(corpo),
            status_code=status_code, resposta=jsonable_encoder(resposta),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Corrida entre duas requisições com a mesma chave: a primeira que
        # gravou vence; a operação em si já foi feita por esta também.
        db.rollback()
