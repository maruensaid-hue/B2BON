from sqlalchemy.orm import Session

from app.models.representante import Representante
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou


def listar(db: Session) -> list[Representante]:
    return db.query(Representante).order_by(Representante.nome).all()


def listar_self_service(db: Session) -> list[Representante]:
    """Só os ativos — é a lista que aparece no `<select>` do checkout
    público, nunca CPF/PIX (ver `RepresentanteSelfServiceSchema`)."""
    return db.query(Representante).filter_by(ativo=True).order_by(Representante.nome).all()


def obter(db: Session, representante_id: int) -> Representante:
    representante = db.query(Representante).filter_by(id=representante_id).one_or_none()
    if representante is None:
        raise NaoEncontrado(f"Representante {representante_id} não encontrado")
    return representante


def obter_ativo(db: Session, representante_id: int) -> Representante:
    """Usado no checkout público — um representante desativado não pode
    ser escolhido num cadastro novo, mesmo que ainda apareça em
    comissões antigas."""
    representante = obter(db, representante_id)
    if not representante.ativo:
        raise RegraNegocioViolada("Representante selecionado não está mais ativo.")
    return representante


def _validar_dados(dados: dict) -> None:
    if not 0 < dados["percentual_comissao"] <= 1:
        raise ValidacaoFalhou('"percentual_comissao" deve ser maior que 0 e no máximo 1 (ex.: 0.10 = 10%).')


def criar(db: Session, dados: dict) -> Representante:
    _validar_dados(dados)
    representante = Representante(**dados)
    db.add(representante)
    db.commit()
    db.refresh(representante)
    return representante


def atualizar(db: Session, representante_id: int, dados: dict) -> Representante:
    representante = obter(db, representante_id)
    _validar_dados(dados)
    for campo, valor in dados.items():
        setattr(representante, campo, valor)
    db.commit()
    db.refresh(representante)
    return representante
