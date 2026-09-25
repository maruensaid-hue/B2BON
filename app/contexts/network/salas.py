"""Corporate Rooms & Buying Rooms (Fase 11). GATE: nenhum dado interno
exposto indevidamente.

Regra única de fronteira (`visivel`): conteúdo `compartilhado` é das duas
empresas da sala; `interno` só da empresa que o criou. Vale para canais,
mensagens, documentos, tarefas, reuniões e stakeholders.

Permissões (`acesso`): só as duas empresas da sala. Se uma empresa definiu
participantes, só eles (EDITOR escreve, LEITOR lê) e os admins dela entram.

Buying Room: o comprador vê título e fase compartilhados pelo vendedor,
nunca o nome interno, valor, probabilidade ou estágio do negócio no CRM.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.contexts.shared.canonical.commercial import BuyingRole
from app.contexts.shared.documentos import TAMANHO_MAXIMO, sha256
from app.models.canal_sala import CanalSala
from app.models.mensagem_sala import MensagemSala
from app.models.sala_compra import SalaCompra
from app.models.sala_corporativa import SalaCorporativa
from app.models.sala_extras import DocumentoSala, ParticipanteSala, ReuniaoSala, StakeholderSala, TarefaSala
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

ESCOPOS = ("compartilhado", "interno")
PAPEIS = ("EDITOR", "LEITOR")
FASES_COMPARTILHADAS = ("DESCOBERTA", "AVALIACAO", "PROPOSTA", "NEGOCIACAO", "DECISAO", "IMPLANTACAO")


@dataclass(frozen=True)
class Acesso:
    sala: SalaCorporativa
    tenant_id: str
    outro_tenant_id: str
    pode_escrever: bool


def visivel(escopo: str, dono_tenant_id: str, consultante: str) -> bool:
    return escopo == "compartilhado" or dono_tenant_id == consultante


def acesso(db: Session, sala_id: int, usuario: Usuario, escrita: bool = False) -> Acesso:
    sala = db.query(SalaCorporativa).filter_by(id=sala_id).one_or_none()
    if sala is None:
        raise NaoEncontrado(f"Sala {sala_id} não encontrada")
    if usuario.tenant_id not in (sala.tenant_id_a, sala.tenant_id_b):
        raise NaoAutorizado("Sua empresa não participa desta sala corporativa.")
    do_meu_lado = db.query(ParticipanteSala).filter_by(sala_id=sala.id, tenant_id=usuario.tenant_id).all()
    admin = usuario.papel in ("admin", "super_admin")
    meu = next((p for p in do_meu_lado if p.usuario_id == usuario.id), None)
    if do_meu_lado and meu is None and not admin:
        raise NaoAutorizado("Você não participa desta sala. Peça acesso a um administrador da sua empresa.")
    pode_escrever = admin or meu is None or meu.papel == "EDITOR"
    if escrita and not pode_escrever:
        raise NaoAutorizado("Seu acesso a esta sala é só de leitura.")
    outro = sala.tenant_id_b if sala.tenant_id_a == usuario.tenant_id else sala.tenant_id_a
    return Acesso(sala, usuario.tenant_id, outro, pode_escrever)


def acesso_pelo_canal(db: Session, canal_id: int, usuario: Usuario, escrita: bool = False) -> Acesso:
    canal = db.query(CanalSala).filter_by(id=canal_id).one_or_none()
    if canal is None:
        raise NaoEncontrado(f"Canal {canal_id} não encontrado")
    return acesso(db, canal.sala_id, usuario, escrita)


def _escopo(escopo: str) -> str:
    if escopo not in ESCOPOS:
        raise ValidacaoFalhou(f"Escopo inválido: {escopo}")
    return escopo


def _registrar(db, acesso_: Acesso, usuario: Usuario, evento: str, entidade: str, registro) -> None:
    db.add(registro)
    db.flush()
    auditoria_service.registrar(db, acesso_.tenant_id, evento, entidade, registro.id, str(usuario.id), {"sala_id": acesso_.sala.id})
    db.commit()
    db.refresh(registro)


# --- Participantes ---------------------------------------------------------------


def definir_participantes(db: Session, sala_id: int, usuario: Usuario, participantes: list[dict]) -> list[dict]:
    """Admin define os participantes do PRÓPRIO lado (nunca do outro)."""
    if usuario.papel not in ("admin", "super_admin"):
        raise NaoAutorizado("Só administradores definem quem participa da sala.")
    a = acesso(db, sala_id, usuario)
    ids = [p["usuario_id"] for p in participantes]
    validos = {u.id for u in db.query(Usuario).filter(Usuario.id.in_(ids or [-1]), Usuario.tenant_id == a.tenant_id).all()}
    if set(ids) - validos:
        raise ValidacaoFalhou("Participantes precisam ser usuários da sua empresa.")
    if any(p.get("papel", "EDITOR") not in PAPEIS for p in participantes):
        raise ValidacaoFalhou("Papel deve ser EDITOR ou LEITOR.")
    db.query(ParticipanteSala).filter_by(sala_id=a.sala.id, tenant_id=a.tenant_id).delete()
    for p in participantes:
        db.add(ParticipanteSala(sala_id=a.sala.id, tenant_id=a.tenant_id, usuario_id=p["usuario_id"], papel=p.get("papel", "EDITOR")))
    auditoria_service.registrar(db, a.tenant_id, "participantes_sala_definidos", "sala_corporativa", a.sala.id, str(usuario.id),
                                {"participantes": ids})
    db.commit()
    return listar_participantes(db, sala_id, usuario)


def listar_participantes(db: Session, sala_id: int, usuario: Usuario) -> list[dict]:
    """Só os do próprio lado: quem participa pela outra empresa é dado dela."""
    a = acesso(db, sala_id, usuario)
    return [
        {"usuario_id": p.usuario_id, "papel": p.papel}
        for p in db.query(ParticipanteSala).filter_by(sala_id=a.sala.id, tenant_id=a.tenant_id).order_by(ParticipanteSala.id)
    ]


# --- Documentos, tarefas, reuniões, stakeholders ----------------------------------------


def adicionar_documento(db, sala_id, usuario, nome_arquivo, tipo_mime, conteudo, escopo, canal_id=None) -> DocumentoSala:
    a = acesso(db, sala_id, usuario, escrita=True)
    if not conteudo or len(conteudo) > TAMANHO_MAXIMO:
        raise ValidacaoFalhou("Arquivo vazio ou acima de 15 MB.")
    if canal_id is not None:
        canal = db.query(CanalSala).filter_by(id=canal_id, sala_id=a.sala.id).one_or_none()
        if canal is None or not visivel(canal.escopo, canal.criado_por, a.tenant_id):
            raise NaoEncontrado(f"Canal {canal_id} não encontrado")
        escopo = canal.escopo  # documento herda a fronteira do canal
    documento = DocumentoSala(sala_id=a.sala.id, tenant_id=a.tenant_id, canal_id=canal_id, escopo=_escopo(escopo),
                              nome_arquivo=nome_arquivo[:255], tipo_mime=tipo_mime or "application/octet-stream",
                              tamanho_bytes=len(conteudo), sha256=sha256(conteudo), conteudo=conteudo,
                              enviado_por_usuario_id=usuario.id)
    _registrar(db, a, usuario, "documento_sala_enviado", "documento_sala", documento)
    return documento


def obter_documento(db: Session, documento_id: int, usuario: Usuario) -> DocumentoSala:
    documento = db.query(DocumentoSala).filter_by(id=documento_id).one_or_none()
    if documento is None:
        raise NaoEncontrado(f"Documento {documento_id} não encontrado")
    a = acesso(db, documento.sala_id, usuario)
    if not visivel(documento.escopo, documento.tenant_id, a.tenant_id):
        raise NaoEncontrado(f"Documento {documento_id} não encontrado")
    return documento


def criar_tarefa(db, sala_id, usuario, dados: dict) -> TarefaSala:
    a = acesso(db, sala_id, usuario, escrita=True)
    escopo = _escopo(dados.get("escopo", "compartilhado"))
    responsavel = dados.get("responsavel_tenant_id")
    if responsavel not in (None, a.tenant_id, a.outro_tenant_id):
        raise ValidacaoFalhou("O responsável deve ser uma das empresas da sala.")
    if escopo == "interno" and responsavel == a.outro_tenant_id:
        raise ValidacaoFalhou("Tarefa interna não pode ter a outra empresa como responsável.")
    tarefa = TarefaSala(sala_id=a.sala.id, tenant_id=a.tenant_id, escopo=escopo, titulo=dados["titulo"],
                        descricao=dados.get("descricao"), responsavel_tenant_id=responsavel,
                        responsavel_usuario_id=dados.get("responsavel_usuario_id") if responsavel == a.tenant_id else None,
                        prazo=dados.get("prazo"), status="ABERTA", criado_por_usuario_id=usuario.id)
    _registrar(db, a, usuario, "tarefa_sala_criada", "tarefa_sala", tarefa)
    return tarefa


def atualizar_tarefa(db, tarefa_id: int, usuario: Usuario, status: str) -> TarefaSala:
    tarefa = db.query(TarefaSala).filter_by(id=tarefa_id).one_or_none()
    if tarefa is None:
        raise NaoEncontrado(f"Tarefa {tarefa_id} não encontrada")
    a = acesso(db, tarefa.sala_id, usuario, escrita=True)
    if not visivel(tarefa.escopo, tarefa.tenant_id, a.tenant_id):
        raise NaoEncontrado(f"Tarefa {tarefa_id} não encontrada")
    if status not in ("ABERTA", "CONCLUIDA", "CANCELADA"):
        raise ValidacaoFalhou("Status inválido.")
    tarefa.status = status
    auditoria_service.registrar(db, a.tenant_id, "tarefa_sala_atualizada", "tarefa_sala", tarefa.id, str(usuario.id), {"status": status})
    db.commit()
    db.refresh(tarefa)
    return tarefa


def agendar_reuniao(db, sala_id, usuario, dados: dict) -> ReuniaoSala:
    a = acesso(db, sala_id, usuario, escrita=True)
    if dados.get("fim") and dados["fim"] < dados["inicio"]:
        raise ValidacaoFalhou("A reunião termina antes de começar.")
    reuniao = ReuniaoSala(sala_id=a.sala.id, tenant_id=a.tenant_id, escopo=_escopo(dados.get("escopo", "compartilhado")),
                          titulo=dados["titulo"], inicio=dados["inicio"], fim=dados.get("fim"), link=dados.get("link"),
                          pauta=dados.get("pauta"), criado_por_usuario_id=usuario.id)
    _registrar(db, a, usuario, "reuniao_sala_agendada", "reuniao_sala", reuniao)
    return reuniao


def adicionar_stakeholder(db, sala_id, usuario, dados: dict) -> StakeholderSala:
    """Padrão `interno`: o mapa que uma empresa faz do comitê da outra (papel,
    notas) é estratégia dela. Compartilhar é escolha explícita."""
    a = acesso(db, sala_id, usuario, escrita=True)
    papel = dados.get("papel", "UNKNOWN")
    if papel not in {r.value for r in BuyingRole}:
        raise ValidacaoFalhou(f"Papel inválido: {papel}")
    if dados.get("lado") not in ("VENDEDOR", "COMPRADOR"):
        raise ValidacaoFalhou("Lado deve ser VENDEDOR ou COMPRADOR.")
    stakeholder = StakeholderSala(sala_id=a.sala.id, tenant_id=a.tenant_id, escopo=_escopo(dados.get("escopo", "interno")),
                                  lado=dados["lado"], nome=dados["nome"], cargo=dados.get("cargo"), papel=papel,
                                  notas=dados.get("notas"), criado_por_usuario_id=usuario.id)
    _registrar(db, a, usuario, "stakeholder_sala_adicionado", "stakeholder_sala", stakeholder)
    return stakeholder


# --- Buying Room ---------------------------------------------------------------------


def compartilhar_negocio(db: Session, sala_id: int, usuario: Usuario, titulo: str | None, fase: str | None) -> dict:
    a = acesso(db, sala_id, usuario, escrita=True)
    vinculo = db.query(SalaCompra).filter_by(sala_corporativa_id=a.sala.id).one_or_none()
    if vinculo is None or vinculo.tenant_id_vendedor != a.tenant_id:
        raise NaoEncontrado("Nenhum negócio seu vinculado a esta sala.")
    if fase is not None and fase not in FASES_COMPARTILHADAS:
        raise ValidacaoFalhou(f"Fase inválida: {fase}")
    vinculo.titulo_compartilhado = titulo
    vinculo.fase_compartilhada = fase
    auditoria_service.registrar(db, a.tenant_id, "sala_compra_compartilhada", "sala_compra", vinculo.id, str(usuario.id),
                                {"fase": fase})
    db.commit()
    return projecao_sala_compra(db, a, vinculo)


def projecao_sala_compra(db: Session, a: Acesso, vinculo: SalaCompra | None) -> dict | None:
    if vinculo is None:
        return None
    if vinculo.tenant_id_vendedor == a.tenant_id:
        from app.models.estagio_funil import EstagioFunil
        from app.models.negocio import Negocio

        negocio = db.get(Negocio, vinculo.negocio_id)
        estagio = db.get(EstagioFunil, negocio.estagio_id) if negocio else None
        return {"e_vendedor": True, "negocio_id": vinculo.negocio_id, "negocio_nome": negocio.nome if negocio else None,
                "estagio_interno": estagio.nome if estagio else None, "visivel_para_comprador": vinculo.visivel_para_comprador,
                "titulo_compartilhado": vinculo.titulo_compartilhado, "fase_compartilhada": vinculo.fase_compartilhada}
    if not vinculo.visivel_para_comprador:
        return None
    return {"e_vendedor": False, "titulo_compartilhado": vinculo.titulo_compartilhado or "Proposta em andamento",
            "fase_compartilhada": vinculo.fase_compartilhada}


# --- Workspace ----------------------------------------------------------------------


def workspace(db: Session, sala_id: int, usuario: Usuario) -> dict:
    a = acesso(db, sala_id, usuario)
    me = a.tenant_id

    def filtrar(modelo):
        return [r for r in db.query(modelo).filter_by(sala_id=a.sala.id).order_by(modelo.id) if visivel(r.escopo, r.tenant_id, me)]

    canais = [c for c in db.query(CanalSala).filter_by(sala_id=a.sala.id).order_by(CanalSala.id) if visivel(c.escopo, c.criado_por, me)]
    ultimas = {
        c.id: db.query(MensagemSala).filter_by(canal_id=c.id).count() for c in canais
    }
    return {
        "sala_id": a.sala.id,
        "outra_empresa": a.outro_tenant_id,
        "pode_escrever": a.pode_escrever,
        "canais": [{"id": c.id, "tipo": c.tipo, "nome": c.nome, "escopo": c.escopo, "mensagens": ultimas[c.id]} for c in canais],
        "documentos": [{"id": d.id, "nome_arquivo": d.nome_arquivo, "escopo": d.escopo, "sha256": d.sha256, "da_minha_empresa": d.tenant_id == me,
                        "canal_id": d.canal_id, "criado_em": d.criado_em} for d in filtrar(DocumentoSala)],
        "tarefas": [{"id": t.id, "titulo": t.titulo, "descricao": t.descricao, "escopo": t.escopo, "status": t.status, "prazo": t.prazo,
                     "responsavel": "NOS" if t.responsavel_tenant_id == me else ("ELES" if t.responsavel_tenant_id else None)}
                    for t in filtrar(TarefaSala)],
        "reunioes": [{"id": r.id, "titulo": r.titulo, "inicio": r.inicio, "fim": r.fim, "link": r.link, "pauta": r.pauta, "escopo": r.escopo}
                     for r in filtrar(ReuniaoSala)],
        "stakeholders": [{"id": s.id, "nome": s.nome, "cargo": s.cargo, "lado": s.lado, "papel": s.papel, "escopo": s.escopo,
                          "notas": s.notas if s.tenant_id == me else None, "da_minha_empresa": s.tenant_id == me}
                         for s in filtrar(StakeholderSala)],
        "sala_de_compra": projecao_sala_compra(db, a, db.query(SalaCompra).filter_by(sala_corporativa_id=a.sala.id).one_or_none()),
        "participantes_do_meu_lado": listar_participantes(db, sala_id, usuario),
    }
