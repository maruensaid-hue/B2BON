"""Relatório de consumo de créditos de IA e de enriquecimento (pesquisa de decisores / provedor de contatos).

Responde, para um período e para o escopo de quem pede (super admin: todas as empresas; admin: a própria empresa e a subárvore):

* quanto cada EMPRESA e cada USUÁRIO consumiu, de IA e de provedor de contatos;
* a franquia e os limites do perfil contratado (plano), e quanto da franquia foi usado;
* as aquisições de créditos adicionais (quantidade, data e valor);
* o consumo ADICIONAL (o que saiu de pacote comprado, promoção/ajuste ou excedente pós-pago), separado do consumo da franquia.

Tudo é lido dos razões que já existem (extrato de IA, razão de enriquecimento, pesquisas e compras): nenhum valor é recalculado de outro jeito, e nada é gravado.
A origem do consumo (franquia × pacote) é derivada do razão, na ordem em que os créditos vencem (franquia antes do pacote); ver `ledger.baldes`.
"""

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento.contract import config as enr_config
from app.contexts.enriquecimento.contract import ledger as enr_ledger
from app.contexts.finops.contract import carteira as ia_carteira
from app.contexts.finops.contract import comercial
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import CompraCreditos, ExecucaoIa, LoteCreditos
from app.models.enriquecimento_creditos import (
    EnriquecimentoCompra,
    EnriquecimentoMovimento,
    PesquisaDecisores,
    PesquisaDecisoresEmpresa,
)
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import tenant_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

Evento, TipoLote = comercial.Evento, comercial.TipoLote

BRT = timedelta(hours=-3)
MAX_DIAS = 366
ESTADOS_PESQUISA_CONTADOS = ("reservada", "enviada", "em_processamento", "concluida", "parcial", "reconciliada")


def _n(valor, casas: int = 2) -> float:
    return float(round(Decimal(str(valor or 0)), casas))


def _dinheiro(valor) -> str:
    return str(round(Decimal(str(valor or 0)), 2))


def periodo(inicio: date | None, fim: date | None, agora: datetime) -> tuple[datetime, datetime]:
    """Intervalo [início, fim) em UTC a partir de datas de Brasília (fim inclusivo para quem pede). Padrão: o mês corrente de Brasília."""
    if inicio is None and fim is None:
        return enr_config.inicio_do_mes(agora), enr_config.fim_do_mes(agora)
    if inicio is None or fim is None:
        raise ValidacaoFalhou("Informe o início e o fim do período.")
    if fim < inicio:
        raise ValidacaoFalhou("O fim do período não pode ser anterior ao início.")
    if (fim - inicio).days > MAX_DIAS:
        raise ValidacaoFalhou(f"O período máximo do relatório é de {MAX_DIAS} dias.")
    return datetime(inicio.year, inicio.month, inicio.day) - BRT, datetime(fim.year, fim.month, fim.day) - BRT + timedelta(days=1)


def _tenants_do_escopo(db: Session, usuario: Usuario, tenant_id: str | None) -> list[Tenant]:
    if usuario.papel == "super_admin":
        tenants = tenant_service.listar_tenants(db)
    else:
        tenants = tenant_service.listar_subarvore(db, usuario.tenant_id)
    if tenant_id is not None:
        tenants = [t for t in tenants if t.id == tenant_id]
        if not tenants:
            raise NaoEncontrado("Empresa não encontrada.")
    return sorted(tenants, key=lambda t: (t.razao_social or "").lower())


def _usuarios(db: Session, tenant_id: str) -> dict[int, Usuario]:
    return {u.id: u for u in db.query(Usuario).filter(Usuario.tenant_id == tenant_id).all()}


def _linha_usuario(usuarios: dict[int, Usuario], usuario_id: int | None) -> dict:
    u = usuarios.get(usuario_id) if usuario_id is not None else None
    return {"usuario_id": usuario_id, "nome": u.nome if u else ("Sistema / sem usuário" if usuario_id is None else f"Usuário #{usuario_id}"),
            "email": u.email if u else None, "papel": u.papel if u else None}


# ------------------------------------------------------------------------------------------------------------------------------ IA


def _ia(db: Session, tenant_id: str, ini: datetime, fim: datetime, usuarios: dict[int, Usuario]) -> dict:
    movimentos = db.query(LoteCreditos.tipo, MovimentoCredito.tipo, func.coalesce(func.sum(MovimentoCredito.quantidade), 0)).join(
        LoteCreditos, LoteCreditos.id == MovimentoCredito.lote_id).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.criado_em >= ini, MovimentoCredito.criado_em < fim,
        MovimentoCredito.tipo.in_((Evento.CONSUMED.value, Evento.REFUNDED.value))).group_by(LoteCreditos.tipo, MovimentoCredito.tipo).all()
    por_lote: dict[str, Decimal] = {}
    for tipo_lote, _tipo_mov, soma in movimentos:  # consumo é negativo e o estorno positivo: líquido = −soma
        por_lote[tipo_lote] = por_lote.get(tipo_lote, Decimal(0)) - Decimal(str(soma))
    franquia = por_lote.get(TipoLote.SUBSCRIPTION.value, Decimal(0))
    adicional_comprado = por_lote.get(TipoLote.TOPUP.value, Decimal(0))
    adicional_bonus = por_lote.get(TipoLote.PROMOTIONAL.value, Decimal(0)) + por_lote.get(TipoLote.ADJUSTMENT.value, Decimal(0))
    excedente = db.query(func.coalesce(func.sum(ExecucaoIa.creditos_excedente), 0)).filter(
        ExecucaoIa.tenant_id == tenant_id, ExecucaoIa.status == "LIQUIDADA", ExecucaoIa.liquidado_em >= ini, ExecucaoIa.liquidado_em < fim).scalar()
    excedente_valor = db.query(func.coalesce(func.sum(MovimentoCredito.receita_brl), 0)).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.tipo == Evento.OVERAGE.value, MovimentoCredito.faturavel.is_(True),
        MovimentoCredito.criado_em >= ini, MovimentoCredito.criado_em < fim).scalar()
    expirado = db.query(func.coalesce(func.sum(MovimentoCredito.quantidade), 0)).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.tipo == Evento.EXPIRED.value, MovimentoCredito.criado_em >= ini,
        MovimentoCredito.criado_em < fim).scalar()

    por_usuario = []
    for usuario_id, creditos, execucoes, exc in db.query(
            ExecucaoIa.usuario_id, func.sum(ExecucaoIa.creditos_liquidados), func.count(ExecucaoIa.id), func.sum(ExecucaoIa.creditos_excedente)).filter(
            ExecucaoIa.tenant_id == tenant_id, ExecucaoIa.status == "LIQUIDADA", ExecucaoIa.liquidado_em >= ini, ExecucaoIa.liquidado_em < fim,
    ).group_by(ExecucaoIa.usuario_id).all():
        por_usuario.append({**_linha_usuario(usuarios, usuario_id), "creditos": _n(creditos), "execucoes": int(execucoes), "excedente": _n(exc)})

    compras = []
    for c in db.query(CompraCreditos).filter(CompraCreditos.tenant_id == tenant_id, CompraCreditos.status == "APROVADA", CompraCreditos.confirmado_em >= ini,
                                             CompraCreditos.confirmado_em < fim).order_by(CompraCreditos.confirmado_em).all():
        compras.append({"produto": "IA", "pacote": c.pacote_codigo, "creditos": int(c.creditos), "valor_brl": _dinheiro(c.preco), "data": c.confirmado_em.isoformat(),
                        "origem": "recarga automática" if c.origem == "AUTO_RECARGA" else "compra manual"})

    total_franquia, _ = ia_carteira.franquia_do_tenant(db, tenant_id)
    consumo_total = franquia + adicional_comprado + adicional_bonus
    return {
        "franquia_mensal": int(total_franquia),
        "consumo_total": _n(consumo_total + Decimal(str(excedente or 0))),
        "consumo_da_franquia": _n(franquia),
        "consumo_adicional": {"pacotes_comprados": _n(adicional_comprado), "bonus_e_ajustes": _n(adicional_bonus), "total": _n(adicional_comprado + adicional_bonus)},
        "consumo_excedente": {"creditos": _n(excedente), "valor_brl": _dinheiro(excedente_valor)},
        "uso_da_franquia_percentual": _n(franquia / total_franquia * 100, 1) if total_franquia else None,
        "expirado": _n(abs(Decimal(str(expirado or 0)))),
        "saldo_atual": _n(ia_carteira.disponivel(db, tenant_id)),
        "por_usuario": sorted(por_usuario, key=lambda x: -x["creditos"]),
        "aquisicoes": compras,
    }


# ---------------------------------------------------------------------------------------------------------------------------- provedor de contatos


def _contatos(db: Session, tenant_id: str, ini: datetime, fim: datetime, agora: datetime, usuarios: dict[int, Usuario]) -> dict:
    consumo_total = -int(db.query(func.coalesce(func.sum(EnriquecimentoMovimento.delta_saldo), 0)).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo.in_(enr_ledger.TIPOS_CONSUMO),
        EnriquecimentoMovimento.criado_em >= ini, EnriquecimentoMovimento.criado_em < fim).scalar() or 0)
    expirado = -int(db.query(func.coalesce(func.sum(EnriquecimentoMovimento.delta_saldo), 0)).filter(
        EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == "EXPIRACAO", EnriquecimentoMovimento.criado_em >= ini,
        EnriquecimentoMovimento.criado_em < fim).scalar() or 0)

    coletor: list[dict] = []
    enr_ledger.baldes(db, tenant_id, agora, janela_dias=max(enr_ledger.JANELA_DE_CONSUMO_DIAS, (agora - ini).days + enr_ledger.JANELA_DE_CONSUMO_DIAS), coletor=coletor)
    origem = {"franquia": 0, "compra": 0}
    for evento in coletor:
        if ini <= evento["em"] < fim and evento["origem"] in origem:
            origem[evento["origem"]] += evento["creditos"]
    da_franquia = min(origem["franquia"], max(consumo_total, 0))
    do_pacote = min(origem["compra"], max(consumo_total - da_franquia, 0))
    outros = max(consumo_total - da_franquia - do_pacote, 0)  # ajuste administrativo, autorização de POC, super admin ou origem não identificável na janela

    filtro = [PesquisaDecisores.tenant_id == tenant_id, PesquisaDecisores.confirmada_em >= ini, PesquisaDecisores.confirmada_em < fim,
              PesquisaDecisores.estado.in_(ESTADOS_PESQUISA_CONTADOS)]
    por_usuario: dict[int, dict] = {}
    for usuario_id, pesquisas, creditos, empresas in db.query(
            PesquisaDecisores.usuario_id, func.count(PesquisaDecisores.id), func.coalesce(func.sum(PesquisaDecisores.creditos_consumidos), 0),
            func.coalesce(func.sum(PesquisaDecisores.total_empresas), 0)).filter(*filtro).group_by(PesquisaDecisores.usuario_id).all():
        por_usuario[usuario_id] = {**_linha_usuario(usuarios, usuario_id), "creditos": int(creditos), "pesquisas": int(pesquisas), "empresas": int(empresas),
                                   "decisores": 0}
    for usuario_id, decisores in db.query(PesquisaDecisores.usuario_id, func.coalesce(func.sum(PesquisaDecisoresEmpresa.decisores_retornados), 0)).join(
            PesquisaDecisoresEmpresa, PesquisaDecisoresEmpresa.pesquisa_id == PesquisaDecisores.id).filter(*filtro).group_by(PesquisaDecisores.usuario_id).all():
        por_usuario[usuario_id]["decisores"] = int(decisores)

    compras = []
    for c in db.query(EnriquecimentoCompra).filter(EnriquecimentoCompra.tenant_id == tenant_id, EnriquecimentoCompra.status == "APROVADA",
                                                   EnriquecimentoCompra.confirmado_em >= ini, EnriquecimentoCompra.confirmado_em < fim).order_by(
            EnriquecimentoCompra.confirmado_em).all():
        compras.append({"produto": "Decisores", "pacote": c.pacote_codigo, "creditos": int(c.creditos), "valor_brl": _dinheiro(c.preco_total_brl),
                        "data": c.confirmado_em.isoformat(), "valido_ate": c.expira_em.isoformat() if c.expira_em else None})

    cfg, motivo = enr_config.config_vigente(db, tenant_id)
    limite_pacote, pacotes_ativos = enr_ledger.limite_por_pacotes(db, tenant_id, agora)
    limite_pesquisa = cfg.limite_creditos_pesquisa if cfg else None
    if limite_pacote is not None and limite_pesquisa is not None and limite_pacote > limite_pesquisa:
        limite_pesquisa = limite_pacote
    franquia = cfg.franquia_creditos if cfg else None
    return {
        "perfil": None if cfg is None else {"origem": cfg.origem, "modo": cfg.modo, "periodicidade": cfg.periodicidade},
        "sem_configuracao": motivo if cfg is None else None,
        "franquia_mensal": franquia,
        "limite_por_pesquisa": limite_pesquisa,
        "limite_por_pesquisa_origem": "pacote adicional" if limite_pacote is not None and limite_pesquisa == limite_pacote else "plano",
        "decisores_por_empresa_max": cfg.decisores_por_empresa_max if cfg else None,
        "empresas_por_pesquisa_max": cfg.itens_por_lote_max if cfg else None,
        "consumo_total": consumo_total,
        "consumo_da_franquia": da_franquia,
        "consumo_adicional": {"pacotes_comprados": do_pacote, "outros": outros, "total": do_pacote + outros},
        "uso_da_franquia_percentual": _n(da_franquia / franquia * 100, 1) if franquia else None,
        "expirado": expirado,
        "saldo_atual": enr_ledger.disponivel(db, tenant_id),
        "pacotes_ativos": pacotes_ativos,
        "por_usuario": sorted(por_usuario.values(), key=lambda x: -x["creditos"]),
        "aquisicoes": compras,
    }


# -------------------------------------------------------------------------------------------------------------------------- relatório


def gerar(db: Session, usuario: Usuario, inicio: date | None = None, fim: date | None = None, tenant_id: str | None = None,
          agora: datetime | None = None) -> dict:
    agora = agora or enr_config.agora_utc()
    ini, limite = periodo(inicio, fim, agora)
    empresas = []
    for tenant in _tenants_do_escopo(db, usuario, tenant_id):
        plano = (db.query(Plano).join(Licenca, Licenca.plano_id == Plano.id).filter(Licenca.tenant_id == tenant.id).first())
        usuarios = _usuarios(db, tenant.id)
        ia, contatos = _ia(db, tenant.id, ini, limite, usuarios), _contatos(db, tenant.id, ini, limite, agora, usuarios)
        empresas.append({"tenant_id": tenant.id, "empresa": tenant.razao_social, "plano": plano.nome if plano else None, "ia": ia, "contatos": contatos})
    empresas.sort(key=lambda e: -(e["ia"]["consumo_total"] + e["contatos"]["consumo_total"]))
    aquisicoes = sorted(
        ({**a, "tenant_id": e["tenant_id"], "empresa": e["empresa"]} for e in empresas for a in e["ia"]["aquisicoes"] + e["contatos"]["aquisicoes"]),
        key=lambda a: a["data"])
    totais = {
        "empresas": len(empresas),
        "ia": {"consumo_total": _n(sum(e["ia"]["consumo_total"] for e in empresas)),
               "consumo_da_franquia": _n(sum(e["ia"]["consumo_da_franquia"] for e in empresas)),
               "consumo_adicional": _n(sum(e["ia"]["consumo_adicional"]["total"] + e["ia"]["consumo_excedente"]["creditos"] for e in empresas))},
        "contatos": {"consumo_total": sum(e["contatos"]["consumo_total"] for e in empresas), "consumo_da_franquia": sum(e["contatos"]["consumo_da_franquia"] for e in empresas),
                  "consumo_adicional": sum(e["contatos"]["consumo_adicional"]["total"] for e in empresas)},
        "aquisicoes": {"quantidade": len(aquisicoes), "creditos": sum(a["creditos"] for a in aquisicoes),
                       "valor_brl": _dinheiro(sum(Decimal(a["valor_brl"]) for a in aquisicoes))},
    }
    return {"periodo": {"inicio": ini.isoformat(), "fim": limite.isoformat(), "fuso": "UTC (datas de Brasília, UTC−3)"}, "totais": totais, "empresas": empresas,
            "aquisicoes": aquisicoes,
            "notas": [
                "Consumo por usuário: IA = execuções liquidadas do usuário; provedor de contatos = créditos das pesquisas de decisores confirmadas por ele.",
                "Consumo adicional = o que saiu de pacote comprado, bônus/ajuste ou excedente pós-pago. A origem é derivada do razão: a franquia, que vence antes, é "
                "consumida primeiro.",
                "Créditos de IA e de enriquecimento são carteiras separadas e nunca se somam.",
            ]}


def para_csv(relatorio: dict) -> str:
    """Relatório em formato de planilha (uma linha por fato, separador `;`, UTF-8 com BOM para o Excel em português)."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(["tipo", "empresa", "plano", "produto", "usuario", "descricao", "creditos", "valor_brl", "data"])
    for e in relatorio["empresas"]:
        base = [e["empresa"], e["plano"] or ""]
        for produto, d in (("IA", e["ia"]), ("Decisores", e["contatos"])):
            escritor.writerow(["franquia", *base, produto, "", "Franquia mensal contratada", d["franquia_mensal"] if d["franquia_mensal"] is not None else "", "", ""])
            if produto == "Decisores":
                escritor.writerow(["limite", *base, produto, "", f"Máx. de créditos por pesquisa ({d['limite_por_pesquisa_origem']})",
                                   d["limite_por_pesquisa"] if d["limite_por_pesquisa"] is not None else "", "", ""])
                escritor.writerow(["limite", *base, produto, "", "Máx. de decisores por empresa", d["decisores_por_empresa_max"] or "", "", ""])
            escritor.writerow(["consumo_empresa", *base, produto, "", "Consumo total", d["consumo_total"], "", ""])
            escritor.writerow(["consumo_empresa", *base, produto, "", "Consumo da franquia", d["consumo_da_franquia"], "", ""])
            adicional = d["consumo_adicional"]
            escritor.writerow(["consumo_adicional", *base, produto, "", "Consumo adicional (pacotes comprados e outros)", adicional["total"], "", ""])
            if produto == "IA":
                escritor.writerow(["consumo_adicional", *base, produto, "", "Excedente pós-pago", d["consumo_excedente"]["creditos"], d["consumo_excedente"]["valor_brl"], ""])
            for u in d["por_usuario"]:
                escritor.writerow(["consumo_usuario", *base, produto, u["nome"], f"{u.get('execucoes', u.get('pesquisas'))} "
                                   f"{'execução(ões)' if produto == 'IA' else 'pesquisa(s)'}", u["creditos"], "", ""])
    for a in relatorio["aquisicoes"]:
        escritor.writerow(["aquisicao", a["empresa"], "", a["produto"], "", f"Pacote {a['pacote']}", a["creditos"], a["valor_brl"], a["data"]])
    return "﻿" + saida.getvalue()
