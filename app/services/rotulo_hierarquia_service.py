from sqlalchemy.orm import Session

from app.models.rotulo_tipo_tenant import RotuloTipoTenant
from app.services.errors import ValidacaoFalhou

# Mesma ordem/conjunto fixo de `tenant_service.TIPOS_TENANT_VALIDOS` — só o
# texto exibido é configurável, a hierarquia por trás (quem pode ser pai de
# quem) não muda.
_ORDEM_TIPOS = ["distribuidor", "revendedor", "cliente"]
_ROTULOS_PADRAO = {"distribuidor": "Master", "revendedor": "Vendedor", "cliente": "Cliente"}


def listar(db: Session) -> list[RotuloTipoTenant]:
    """Garante as 3 linhas na primeira leitura (idempotente) — sustenta
    tanto um banco criado via `Base.metadata.create_all` sem rodar a
    migração (testes) quanto uma migração aplicada de fato em produção."""
    existentes = {linha.tipo: linha for linha in db.query(RotuloTipoTenant).all()}
    faltando = [tipo for tipo in _ORDEM_TIPOS if tipo not in existentes]
    for tipo in faltando:
        nova = RotuloTipoTenant(tipo=tipo, rotulo=_ROTULOS_PADRAO[tipo])
        db.add(nova)
        existentes[tipo] = nova
    if faltando:
        db.commit()
    return [existentes[tipo] for tipo in _ORDEM_TIPOS]


def atualizar(
    db: Session, rotulo_distribuidor: str, rotulo_revendedor: str, rotulo_cliente: str
) -> list[RotuloTipoTenant]:
    valores = {
        "distribuidor": rotulo_distribuidor.strip(),
        "revendedor": rotulo_revendedor.strip(),
        "cliente": rotulo_cliente.strip(),
    }
    for tipo, rotulo in valores.items():
        if not rotulo:
            raise ValidacaoFalhou(f'O rótulo de "{tipo}" não pode ser vazio.')

    linhas = {linha.tipo: linha for linha in listar(db)}
    for tipo, rotulo in valores.items():
        linhas[tipo].rotulo = rotulo
    db.commit()
    return [linhas[tipo] for tipo in _ORDEM_TIPOS]
