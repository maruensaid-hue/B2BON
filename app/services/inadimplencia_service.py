"""Quadro "Clientes inadimplentes" do MAP (pedido do PO em 18/11/2026, opção "as duas").

Duas fontes, dois quadros:

1. Parcelas a receber dos negócios ganhos (`ParcelaNegocio`), lançadas pelo vendedor. Em atraso = vencimento antes de hoje (Brasília) e sem `pago_em`.
   Visibilidade igual à do MAP-Contas: `user` (vendedor) vê só as parcelas dos negócios dele; admin/super_admin veem a subárvore de tenants
   (`tenant_service.tenant_ids_no_escopo`, que também amplia a leitura do RLS) e filtram por tenant, vendedor e representante. O representante NÃO ganha acesso
   às parcelas dos clientes dos tenants que vendeu: é dado comercial do tenant com os clientes dele, não da venda do B2B ON (decisão registrada no CHANGELOG).
2. Licenças da B2B ON vencidas e sem pagamento confirmado (`Licenca.data_expiracao` no passado, cobrança direta). Quem vê: super_admin (todos), admin de
   distribuidor/revendedor (os tenants abaixo dele) e o usuário vinculado a um representante (os tenants que ele vendeu).

Em ambos, cada linha traz o tenant, o representante, a revenda e o distribuidor (o primeiro ancestral, incluindo o próprio tenant, de cada tipo).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import rls
from app.models.conta import Conta
from app.models.licenca import Licenca
from app.models.negocio import Negocio
from app.models.parcela_negocio import ParcelaNegocio
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auditoria_service, tenant_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

_FUSO_BRASILIA = timedelta(hours=-3)  # sem horário de verão desde 2019
_DIAS_CARENCIA_LICENCA = 3  # mesma carência de `tenant_service.suspender_licencas_vencidas`
_PAPEIS_GESTOR = ("admin", "super_admin")


def hoje_brasilia(agora: datetime | None = None) -> date:
    return ((agora or datetime.now(UTC)) + _FUSO_BRASILIA).date()


# --- Hierarquia (tenant é tabela global, sem RLS) ---------------------------------------------------------------------------------------------------------

class _Hierarquia:
    """Memoiza tenants, nomes de representante e a revenda/distribuidor de cada tenant numa chamada."""

    def __init__(self, db: Session):
        self.db = db
        self._tenants: dict[str, Tenant | None] = {}
        self._representantes: dict[int, str | None] = {}

    def tenant(self, tenant_id: str | None) -> Tenant | None:
        if tenant_id is None:
            return None
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = self.db.query(Tenant).filter_by(id=tenant_id).one_or_none()
        return self._tenants[tenant_id]

    def ancestral_do_tipo(self, tenant_id: str, tipo: str) -> Tenant | None:
        atual, vistos = self.tenant(tenant_id), set()
        while atual is not None and atual.id not in vistos:
            if atual.tipo == tipo:
                return atual
            vistos.add(atual.id)
            atual = self.tenant(atual.tenant_pai_id)
        return None

    def representante_nome(self, representante_id: int | None) -> str | None:
        if representante_id is None:
            return None
        if representante_id not in self._representantes:
            rep = self.db.get(Representante, representante_id)
            self._representantes[representante_id] = rep.nome if rep else None
        return self._representantes[representante_id]

    def colunas(self, tenant_id: str) -> dict:
        tenant = self.tenant(tenant_id)
        revenda = self.ancestral_do_tipo(tenant_id, "revendedor")
        distribuidor = self.ancestral_do_tipo(tenant_id, "distribuidor")
        representante_id = tenant.representante_id if tenant else None
        return {
            "tenant_id": tenant_id,
            "tenant_nome": tenant.razao_social if tenant else tenant_id,
            "representante_id": representante_id,
            "representante_nome": self.representante_nome(representante_id),
            "revenda_id": revenda.id if revenda else None,
            "revenda_nome": revenda.razao_social if revenda else None,
            "distribuidor_id": distribuidor.id if distribuidor else None,
            "distribuidor_nome": distribuidor.razao_social if distribuidor else None,
        }


def _opcoes(linhas: list[dict]) -> dict:
    """Valores dos filtros a partir do que a pessoa já pode ver (nunca oferece um tenant/vendedor fora do escopo dela)."""

    def pares(chave_id: str, chave_nome: str) -> list[dict]:
        vistos = {linha[chave_id]: linha[chave_nome] for linha in linhas if linha.get(chave_id) is not None}
        return sorted(({"id": k, "nome": v or str(k)} for k, v in vistos.items()), key=lambda item: item["nome"].lower())

    return {
        "tenants": pares("tenant_id", "tenant_nome"),
        "vendedores": pares("vendedor_usuario_id", "vendedor_nome"),
        "representantes": pares("representante_id", "representante_nome"),
        "revendas": pares("revenda_id", "revenda_nome"),
        "distribuidores": pares("distribuidor_id", "distribuidor_nome"),
    }


def _filtrar(linhas: list[dict], filtros: dict) -> list[dict]:
    return [linha for linha in linhas if all(valor is None or linha.get(chave) == valor for chave, valor in filtros.items())]


def _resumo(linhas: list[dict], chave_valor: str) -> dict:
    return {
        "total_em_atraso": round(sum(linha[chave_valor] or 0 for linha in linhas), 2),
        "quantidade": len(linhas),
        "clientes": len({linha["cliente_chave"] for linha in linhas}),
        "maior_atraso_dias": max((linha["dias_atraso"] for linha in linhas), default=0),
    }


# --- Quadro 1: parcelas dos negócios ganhos -----------------------------------------------------------------------------------------------------------

def quadro_parcelas(
    db: Session,
    usuario: Usuario,
    *,
    tenant_id_selecionado: str | None = None,
    vendedor_usuario_id: int | None = None,
    representante_id: int | None = None,
    revenda_id: str | None = None,
    distribuidor_id: str | None = None,
    hoje: date | None = None,
) -> dict:
    hoje = hoje or hoje_brasilia()
    tenant_ids = tenant_service.tenant_ids_no_escopo(db, usuario, tenant_id_selecionado)  # antes das consultas: amplia a leitura do RLS para a subárvore
    consulta = (
        db.query(ParcelaNegocio, Negocio)
        .join(Negocio, Negocio.id == ParcelaNegocio.negocio_id)
        .filter(
            ParcelaNegocio.tenant_id.in_(tenant_ids),
            ParcelaNegocio.pago_em.is_(None),
            ParcelaNegocio.vencimento < hoje,
            Negocio.perdido_em.is_(None),
        )
    )
    if usuario.papel == "user":
        consulta = consulta.filter(Negocio.vendedor_usuario_id == usuario.id)
    pares = consulta.order_by(ParcelaNegocio.vencimento, ParcelaNegocio.id).all()

    conta_ids = {negocio.conta_id for _, negocio in pares}
    contas = {c.id: c for c in db.query(Conta).filter(Conta.id.in_(conta_ids)).all()} if conta_ids else {}
    vendedor_ids = {negocio.vendedor_usuario_id for _, negocio in pares if negocio.vendedor_usuario_id}
    vendedores = {u.id: u.nome for u in db.query(Usuario).filter(Usuario.id.in_(vendedor_ids)).all()} if vendedor_ids else {}

    hierarquia = _Hierarquia(db)
    linhas = []
    for parcela, negocio in pares:
        conta = contas.get(negocio.conta_id)
        linhas.append({
            "parcela_id": parcela.id,
            "negocio_id": negocio.id,
            "negocio_nome": negocio.nome,
            "conta_id": negocio.conta_id,
            "cliente": (conta.nome_fantasia or conta.nome) if conta else f"Conta {negocio.conta_id}",
            "cliente_chave": f"{parcela.tenant_id}:{negocio.conta_id}",
            "vendedor_usuario_id": negocio.vendedor_usuario_id,
            "vendedor_nome": vendedores.get(negocio.vendedor_usuario_id),
            "numero": parcela.numero,
            "valor": parcela.valor,
            "vencimento": parcela.vencimento,
            "dias_atraso": (hoje - parcela.vencimento).days,
            "observacao": parcela.observacao,
            **hierarquia.colunas(parcela.tenant_id),
        })

    opcoes = _opcoes(linhas)
    if usuario.papel == "user":
        vendedor_usuario_id = None  # o vendedor já está travado nele mesmo (mesma regra do MAP-Contas: filtro de outro é ignorado, não é 403)
    linhas = _filtrar(linhas, {"vendedor_usuario_id": vendedor_usuario_id, "representante_id": representante_id,
                               "revenda_id": revenda_id, "distribuidor_id": distribuidor_id})
    return {"hoje": hoje, "resumo": _resumo(linhas, "valor"), "linhas": linhas, "opcoes": opcoes}


# --- Quadro 2: licenças da B2B ON vencidas ------------------------------------------------------------------------------------------------------------

def _representante_do_usuario(db: Session, usuario: Usuario) -> Representante | None:
    return db.query(Representante).filter_by(usuario_id=usuario.id, ativo=True).one_or_none()


def _tenants_de_licenca_visiveis(db: Session, usuario: Usuario) -> set[str] | None:
    """Tenants cuja licença a pessoa pode acompanhar; `None` = nenhum acesso a este quadro."""
    visiveis: set[str] = set()
    acesso = False
    if usuario.papel == "super_admin":
        return set(tenant_service.tenant_ids_no_escopo(db, usuario, None))
    tenant_proprio = db.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none()
    if usuario.papel == "admin" and tenant_proprio is not None and tenant_proprio.tipo in ("distribuidor", "revendedor"):
        acesso = True
        visiveis |= {t.id for t in tenant_service.listar_subarvore(db, usuario.tenant_id)} - {usuario.tenant_id}  # a própria licença não é "cliente" dele
    representante = _representante_do_usuario(db, usuario)
    if representante is not None:
        acesso = True
        visiveis |= {t.id for t in db.query(Tenant).filter_by(representante_id=representante.id).all()}
    if not acesso:
        return None
    rls.ampliar_leitura(db, sorted(visiveis | {usuario.tenant_id}))  # só leitura, exatamente o que esta regra autorizou
    return visiveis


def acesso(db: Session, usuario: Usuario) -> dict:
    return {
        "parcelas": True,
        "licencas": _tenants_de_licenca_visiveis(db, usuario) is not None,
        "notas_daily": usuario.papel in _PAPEIS_GESTOR,
    }


def quadro_licencas(
    db: Session,
    usuario: Usuario,
    *,
    tenant_id_selecionado: str | None = None,
    representante_id: int | None = None,
    revenda_id: str | None = None,
    distribuidor_id: str | None = None,
    hoje: date | None = None,
) -> dict:
    hoje = hoje or hoje_brasilia()
    visiveis = _tenants_de_licenca_visiveis(db, usuario)
    if visiveis is None:
        raise NaoAutorizado("O quadro de licenças é da gestão da B2B ON, de distribuidores, revendas e representantes.")
    if not visiveis:
        return {"hoje": hoje, "resumo": _resumo([], "valor_mensal"), "linhas": [], "opcoes": _opcoes([])}

    resultados = (
        db.query(Licenca, Tenant, Plano)
        .join(Tenant, Tenant.id == Licenca.tenant_id)
        .join(Plano, Plano.id == Licenca.plano_id)
        .filter(
            Licenca.tenant_id.in_(visiveis),
            Licenca.status.in_(("ativa", "suspensa")),
            Licenca.data_expiracao.isnot(None),
            Tenant.modo_cobranca == "direta",
            Tenant.ativo.is_(True),
            Tenant.demo_expira_em.is_(None),
        )
        .all()
    )
    hierarquia = _Hierarquia(db)
    linhas = []
    for licenca, tenant, plano in resultados:
        expiracao = licenca.data_expiracao if licenca.data_expiracao.tzinfo else licenca.data_expiracao.replace(tzinfo=UTC)
        vencimento = hoje_brasilia(expiracao)
        dias = (hoje - vencimento).days
        if dias <= 0:
            continue
        if licenca.status == "suspensa":
            situacao = "suspensa"
        elif licenca.declaracao_pagamento_em is not None:
            situacao = "pagamento_declarado"
        elif dias <= _DIAS_CARENCIA_LICENCA:
            situacao = "em_carencia"
        else:
            situacao = "vencida"
        linhas.append({
            "licenca_id": licenca.id,
            "cliente": tenant.razao_social,
            "cliente_chave": tenant.id,
            "plano_nome": plano.nome,
            "valor_mensal": plano.preco_mensal,
            "vencimento": vencimento,
            "dias_atraso": dias,
            "situacao": situacao,
            **hierarquia.colunas(tenant.id),
        })
    linhas.sort(key=lambda linha: -linha["dias_atraso"])
    opcoes = _opcoes(linhas)
    linhas = _filtrar(linhas, {"tenant_id": tenant_id_selecionado, "representante_id": representante_id,
                               "revenda_id": revenda_id, "distribuidor_id": distribuidor_id})
    return {"hoje": hoje, "resumo": _resumo(linhas, "valor_mensal"), "linhas": linhas, "opcoes": opcoes}


# --- Parcelas de um negócio (lançadas pelo vendedor no CRM) ---------------------------------------------------------------------------------------------

def _negocio(db: Session, tenant_id: str, negocio_id: int) -> Negocio:
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado("Oportunidade não encontrada.")
    return negocio


def _parcela(db: Session, tenant_id: str, negocio_id: int, parcela_id: int) -> ParcelaNegocio:
    parcela = db.query(ParcelaNegocio).filter_by(id=parcela_id, negocio_id=negocio_id, tenant_id=tenant_id).one_or_none()
    if parcela is None:
        raise NaoEncontrado("Parcela não encontrada.")
    return parcela


def listar_parcelas(db: Session, tenant_id: str, negocio_id: int, hoje: date | None = None) -> dict:
    hoje = hoje or hoje_brasilia()
    negocio = _negocio(db, tenant_id, negocio_id)
    parcelas = (db.query(ParcelaNegocio).filter_by(negocio_id=negocio_id, tenant_id=tenant_id)
                .order_by(ParcelaNegocio.vencimento, ParcelaNegocio.numero).all())
    return {
        "ganho": negocio.ganho_em is not None,
        "valor_negocio": negocio.valor,
        "parcelas": [
            {
                "id": p.id, "numero": p.numero, "valor": p.valor, "vencimento": p.vencimento, "pago_em": p.pago_em, "observacao": p.observacao,
                "em_atraso": p.pago_em is None and p.vencimento < hoje,
                "dias_atraso": (hoje - p.vencimento).days if p.pago_em is None and p.vencimento < hoje else 0,
            }
            for p in parcelas
        ],
    }


def _validar(valor: float, observacao: str | None) -> None:
    if valor is None or valor <= 0:
        raise ValidacaoFalhou("O valor da parcela precisa ser maior que zero.")
    if observacao is not None and len(observacao) > 300:
        raise ValidacaoFalhou("A observação aceita até 300 caracteres.")


def criar_parcela(db: Session, tenant_id: str, negocio_id: int, ator_id: str | None, *, valor: float, vencimento: date,
                  observacao: str | None = None) -> ParcelaNegocio:
    negocio = _negocio(db, tenant_id, negocio_id)
    if negocio.ganho_em is None:
        raise ValidacaoFalhou("Parcelas só podem ser lançadas em negócio ganho.")
    _validar(valor, observacao)
    ultimo = db.query(func.max(ParcelaNegocio.numero)).filter_by(negocio_id=negocio_id, tenant_id=tenant_id).scalar() or 0
    parcela = ParcelaNegocio(tenant_id=tenant_id, negocio_id=negocio_id, numero=ultimo + 1, valor=valor, vencimento=vencimento,
                             observacao=(observacao or "").strip() or None, criado_por_usuario_id=int(ator_id) if ator_id else None)
    db.add(parcela)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "parcela_negocio_criada", "parcela_negocio", parcela.id, ator_id,
                                {"negocio_id": negocio_id, "valor": valor, "vencimento": vencimento.isoformat()})
    db.commit()
    db.refresh(parcela)
    return parcela


def atualizar_parcela(db: Session, tenant_id: str, negocio_id: int, parcela_id: int, ator_id: str | None, *, valor: float,
                      vencimento: date, pago_em: date | None, observacao: str | None) -> ParcelaNegocio:
    parcela = _parcela(db, tenant_id, negocio_id, parcela_id)
    _validar(valor, observacao)
    parcela.valor, parcela.vencimento, parcela.pago_em = valor, vencimento, pago_em
    parcela.observacao = (observacao or "").strip() or None
    auditoria_service.registrar(db, tenant_id, "parcela_negocio_atualizada", "parcela_negocio", parcela.id, ator_id,
                                {"negocio_id": negocio_id, "valor": valor, "vencimento": vencimento.isoformat(),
                                 "pago_em": pago_em.isoformat() if pago_em else None})
    db.commit()
    db.refresh(parcela)
    return parcela


def excluir_parcela(db: Session, tenant_id: str, negocio_id: int, parcela_id: int, ator_id: str | None) -> None:
    parcela = _parcela(db, tenant_id, negocio_id, parcela_id)
    auditoria_service.registrar(db, tenant_id, "parcela_negocio_excluida", "parcela_negocio", parcela.id, ator_id,
                                {"negocio_id": negocio_id, "valor": parcela.valor, "vencimento": parcela.vencimento.isoformat()})
    db.delete(parcela)
    db.commit()
