"""Varredura sistemática de isolamento entre tenants (V5.2.1, Fase 1).

Cenário: o tenant B (vítima) recebe o seed de demonstração (CRM, prospecção, licitações, relacionamento) e um usuário de B cria conteúdo
de rede. O tenant A (atacante, admin com licença ativa, sem dados) chama TODAS as rotas autenticadas por sessão com ids reais de B no
caminho, na query e no corpo. Dois detectores independentes:

1. Diferença do banco inteiro: nenhuma linha de B pode ser alterada/excluída, nenhuma linha nova pode apontar (FK) para objeto de B nem
   nascer "dentro" de objeto de B;
2. Vazamento em resposta: nenhum texto distintivo de B pode aparecer em resposta 2xx entregue a A.

O que é cruzamento legítimo por desenho (rede social entre empresas) fica em `EXCECOES_*`, cada uma com justificativa.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.params import File, Form
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.core.rate_limit import limitador_api, limitador_auth, limitador_demo, limitador_ia, limitador_portal
from app.db.base import Base
from app.main import app
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service
from app.services.demo import semente

RAIZ = Path(__file__).resolve().parents[2]
TENANT_A = "tenant-a-atacante"
TENANT_B = "tenant-b-vitima"

# Rotas em que o usuário de A pode legitimamente receber dado público de B (diretório e rede social são abertos entre assinantes por
# desenho; o que é privado de B continua coberto pelos marcadores e pela comparação de banco).
ROTAS_PUBLICAS_ENTRE_ASSINANTES = (
    "/api/v1/rede-social/empresas",
    "/api/v1/rede-social/posts",
    "/api/v1/rede-social/intents",
    "/api/v1/rede-social/perfil",
    "/api/v1/rede-social/relacionamentos",
    "/api/v1/rede/",
    "/api/v1/rede-social/representantes",
)
# Tabelas cuja criação por A apontando para B é o próprio mecanismo da rede (pedido de conexão, mensagem entre empresas, etc.).
TABELAS_CRUZAMENTO_LEGITIMO = {
    "conexao_empresa", "seguidor_empresa", "mensagem_rede_social", "notificacao_rede_social", "relacionamento_empresarial",
    "sala_corporativa", "canal_sala", "mensagem_sala", "participante_sala", "audit_log", "auditoria",
    # Interação social em post de outra empresa (comentar, reagir, repostar) é o propósito do feed; o bloqueio entre empresas
    # é validado à parte (test_post_rede_social).
    "post_rede_social", "comentario_post", "reacao_post", "midia_post",
}
IGNORAR_METODOS = {"HEAD", "OPTIONS"}


def _carregar_inventario():
    caminho = RAIZ / "scripts" / "qualidade" / "inventario_rotas.py"
    spec = importlib.util.spec_from_file_location("inventario_rotas", caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["inventario_rotas"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# --- geração de requisições -----------------------------------------------------------------------------------------------------------


class Entidades:
    """Resolve `conta_id`, `negocio_id`... para ids reais de B (e de qualquer tenant, como reserva)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.tabelas = {t.name: t for t in Base.metadata.sorted_tables}
        self._cache: dict[str, list[int]] = {}

    def _tabela_para(self, base: str) -> str | None:
        if base in self.tabelas:
            return base
        for nome in self.tabelas:
            if nome.endswith("_" + base) or nome.startswith(base + "_"):
                return nome
        if base.endswith("s") and base[:-1] in self.tabelas:
            return base[:-1]
        return None

    def ids(self, campo: str) -> list[int]:
        base = re.sub(r"_id$", "", campo)
        if base in ("vendedor_usuario", "responsavel_usuario", "criado_por_usuario", "usuario"):
            base = "usuario"
        if base in self._cache:
            return self._cache[base]
        nome = self._tabela_para(base)
        resultado: list[int] = []
        if nome is not None:
            tabela = self.tabelas[nome]
            if "id" in tabela.c:
                consulta = tabela.select()
                if "tenant_id" in tabela.c:
                    consulta = consulta.where(tabela.c.tenant_id == TENANT_B)
                linhas = self.db.execute(consulta.limit(200)).fetchall()
                resultado = [r._mapping["id"] for r in linhas if isinstance(r._mapping["id"], int)]
        self._cache[base] = resultado
        return resultado


USO = {"real": False, "tinha_id": False}
TERMOS_BUSCA: list[str] = []  # preenchido pelo cenário com textos distintivos de B (nome de conta, domínio de e-mail, nome de pessoa)
BUSCA_RE = re.compile(r"^(q|busca|termo|search|filtro|texto|query|nome|cnpj)$", re.I)
MODO = {"todos": False}  # 2ª tentativa após 422: preenche todas as propriedades do corpo, não só as obrigatórias


def _escolher(ids: list[int], variante: int) -> int:
    USO["tinha_id"] = True
    if not ids:
        return 1 + variante
    USO["real"] = True
    return ids[[0, len(ids) // 2, -1][variante % 3]]


def _valor_texto(nome: str, esquema: dict) -> str:
    if "enum" in esquema:
        return esquema["enum"][0]
    formato = esquema.get("format")
    if formato == "date":
        return "2026-10-15"
    if formato == "date-time":
        return "2026-10-15T10:00:00"
    if formato == "email":
        return "x@exemplo.com.br"
    if formato == "uri":
        return "https://exemplo.com.br"
    padrao = esquema.get("pattern", "")
    if padrao:
        if "0[1-9]|1[0-2]" in padrao and r"\d{4}" in padrao:
            return "2026-10"
        if r"\d{4}-\d{2}-\d{2}" in padrao:
            return "2026-10-15"
    if re.search(r"tenant", nome, re.I):
        return TENANT_B
    minimo = esquema.get("minLength", 1)
    return ("x" * max(minimo, 3))[: esquema.get("maxLength", 200)]


def _gerar(esquema: dict, defs: dict, nome: str, entidades: Entidades, variante: int, profundidade: int = 0):
    if "$ref" in esquema:
        return _gerar(defs[esquema["$ref"].split("/")[-1]], defs, nome, entidades, variante, profundidade)
    if "default" in esquema and not re.search(r"(tenant|_id$)", nome, re.I):
        return esquema["default"]
    for chave in ("anyOf", "oneOf"):
        if chave in esquema:
            opcoes = [o for o in esquema[chave] if o.get("type") != "null"]
            return _gerar(opcoes[0], defs, nome, entidades, variante, profundidade) if opcoes else None
    if "allOf" in esquema:
        return _gerar(esquema["allOf"][0], defs, nome, entidades, variante, profundidade)
    tipo = esquema.get("type")
    if tipo == "string":
        return _valor_texto(nome, esquema)
    if tipo == "integer":
        if nome.endswith("_id") or nome == "id":
            return _escolher(entidades.ids(nome), variante)
        return max(int(esquema.get("minimum", 1)), 1)
    if tipo == "number":
        return float(max(esquema.get("minimum", 1), 1))
    if tipo == "boolean":
        return False
    if tipo == "array":
        item = esquema.get("items", {})
        if item.get("type") == "integer" and re.search(r"ids$", nome):
            # operações em lote: a lista leva ids reais de B (ex.: conta_ids, decisor_ids, ordem_ids)
            alias = {"ordem_ids": "estagio_id"}.get(nome, nome[:-1])
            reais = entidades.ids(alias)
            USO["tinha_id"] = USO["tinha_id"] or True
            USO["real"] = USO["real"] or bool(reais)
            return (reais[:6] or [1, 2, 3]) if variante == 0 else (reais[-3:] or [1, 2, 3])
        minimo = esquema.get("minItems", 0)
        if minimo and profundidade < 3:
            return [_gerar(esquema.get("items", {}), defs, nome, entidades, variante, profundidade + 1) for _ in range(minimo)]
        return []
    if tipo == "object" or "properties" in esquema:
        if profundidade > 4:
            return {}
        saida = {}
        for campo, sub in esquema.get("properties", {}).items():
            if MODO["todos"] or campo in esquema.get("required", []) or re.search(r"(tenant|_id$)", campo, re.I):
                saida[campo] = _gerar(sub, defs, campo, entidades, variante, profundidade + 1)
        return saida
    return "x"


def _esquema_do_tipo(anotacao) -> tuple[dict, dict]:
    esquema = TypeAdapter(anotacao).json_schema(ref_template="#/$defs/{model}")
    return esquema, esquema.get("$defs", {})


def _todos(dependant, atributo: str) -> list:
    """Parâmetros do endpoint E das sub-dependências (ex.: `participante_id` declarado dentro de `_por_conta`)."""
    achados = list(getattr(dependant, atributo))
    for sub in dependant.dependencies:
        achados.extend(_todos(sub, atributo))
    unicos = {}
    for p in achados:
        unicos.setdefault(p.name, p)
    return list(unicos.values())


def montar_requisicao(ctx, entidades: Entidades, variante: int) -> dict | None:
    """Devolve kwargs para `client.request`, ou None quando não há como montar (rota fora do alcance da varredura)."""
    caminho = ctx.path
    for parametro in _todos(ctx.dependant, "path_params"):
        nome = parametro.name
        anotacao = parametro.field_info.annotation
        if re.search(r"tenant", nome, re.I):
            valor = TENANT_B
        elif anotacao is int:
            ids = entidades.ids(nome if nome != "id" else _substantivo_anterior(ctx.path, nome))
            valor = _escolher(ids, variante)
        else:
            valor = "x"
        caminho = caminho.replace("{" + nome + "}", str(valor))
    caminho = re.sub(r"\{[^}]*:path\}", "x", caminho)
    params: dict = {}
    for parametro in _todos(ctx.dependant, "query_params"):
        nome = parametro.name
        anotacao = parametro.field_info.annotation
        obrigatorio = parametro.field_info.is_required()
        eh_busca = bool(BUSCA_RE.match(nome)) and bool(TERMOS_BUSCA)
        alvo_b = bool(re.search(r"tenant", nome, re.I)) or (nome.endswith("_id") and anotacao in (int, int | None)) or eh_busca
        if not obrigatorio and not alvo_b:
            continue
        if re.search(r"tenant", nome, re.I):
            params[nome] = TENANT_B
        elif eh_busca:
            params[nome] = TERMOS_BUSCA[variante % len(TERMOS_BUSCA)]
        elif nome.endswith("_id") or nome == "id":
            params[nome] = _escolher(entidades.ids(nome), variante)
        else:
            esquema, _ = _esquema_do_tipo(anotacao)
            esquema = {"type": "string", **esquema} if "type" not in esquema and "anyOf" not in esquema else esquema
            if "anyOf" in esquema:
                esquema = next((o for o in esquema["anyOf"] if o.get("type") != "null"), {"type": "string"})
            tipo = esquema.get("type")
            params[nome] = (1 if tipo == "integer" else 1.0 if tipo == "number" else "true" if tipo == "boolean" else _valor_texto(nome, esquema))
            if nome == "periodo" or "mes" in nome:
                params[nome] = "2026-10"
    requisicao: dict = {"url": caminho, "params": params}
    corpo = ctx.dependant.body_params
    if corpo:
        formularios = [p for p in corpo if isinstance(p.field_info, (Form, File))]
        if formularios:
            dados, arquivos = {}, {}
            for p in formularios:
                if isinstance(p.field_info, File):
                    arquivos[p.name] = ("anexo.txt", b"conteudo de teste", "text/plain")
                else:
                    esquema, defs = _esquema_do_tipo(p.field_info.annotation)
                    dados[p.name] = _gerar(esquema, defs, p.name, entidades, variante)
            requisicao["data"] = {k: v for k, v in dados.items() if v is not None}
            if arquivos:
                requisicao["files"] = arquivos
        elif len(corpo) == 1 and not getattr(corpo[0].field_info, "embed", False):
            esquema, defs = _esquema_do_tipo(corpo[0].field_info.annotation)
            requisicao["json"] = _gerar(esquema, defs, corpo[0].name, entidades, variante)
        else:
            saida = {}
            for p in corpo:
                esquema, defs = _esquema_do_tipo(p.field_info.annotation)
                saida[p.name] = _gerar(esquema, defs, p.name, entidades, variante)
            requisicao["json"] = saida
    return requisicao


def _substantivo_anterior(caminho: str, nome: str) -> str:
    partes = [p for p in caminho.split("/") if p]
    indice = partes.index("{" + nome + "}")
    anterior = partes[indice - 1] if indice else "x"
    return anterior.replace("-", "_").rstrip("s") + "_id"


# --- fotografia do banco --------------------------------------------------------------------------------------------------------------


def fotografar(db: Session) -> dict[str, dict[tuple, tuple]]:
    db.expire_all()
    foto: dict[str, dict[tuple, tuple]] = {}
    for tabela in Base.metadata.sorted_tables:
        chaves = [c.name for c in tabela.primary_key.columns]
        if not chaves:
            continue
        foto[tabela.name] = {tuple(r._mapping[c] for c in chaves): tuple(r) for r in db.execute(tabela.select()).fetchall()}
    return foto


def _mapa_fk() -> dict[str, list[tuple[int, str]]]:
    """tabela -> [(posição da coluna, tabela referenciada)] para FKs que NÃO apontam para `tenant`."""
    mapa = {}
    for tabela in Base.metadata.sorted_tables:
        colunas = [c.name for c in tabela.columns]
        itens = []
        for coluna in tabela.columns:
            for fk in coluna.foreign_keys:
                alvo = fk.column.table.name
                if alvo != "tenant":
                    itens.append((colunas.index(coluna.name), alvo))
        mapa[tabela.name] = itens
    return mapa


class Dono:
    """Resolve o tenant dono de uma linha: coluna `tenant_id` ou, na falta dela, a primeira FK que leve a um dono."""

    def __init__(self, foto: dict[str, dict[tuple, tuple]]) -> None:
        self.foto = foto
        self.tabelas = {t.name: t for t in Base.metadata.sorted_tables}
        self.fk = _mapa_fk()

    def de(self, nome: str, linha: tuple, fundo: int = 0) -> str | None:
        tabela = self.tabelas[nome]
        colunas = [c.name for c in tabela.columns]
        if "tenant_id" in colunas:
            return linha[colunas.index("tenant_id")]
        if fundo > 4:
            return None
        for posicao, alvo in self.fk.get(nome, []):
            valor = linha[posicao]
            if valor is None:
                continue
            origem = self.foto.get(alvo, {}).get((valor,))
            if origem is not None:
                dono = self.de(alvo, origem, fundo + 1)
                if dono is not None:
                    return dono
        return None

    def referencias_a(self, nome: str, linha: tuple, tenant: str) -> list[str]:
        """Objetos (não-tenant) que a linha referencia e que pertencem a `tenant`."""
        achados = []
        for posicao, alvo in self.fk.get(nome, []):
            valor = linha[posicao]
            if valor is None:
                continue
            origem = self.foto.get(alvo, {}).get((valor,))
            if origem is not None and self.de(alvo, origem) == tenant:
                achados.append(f"{alvo}#{valor}")
        return achados


# --- marcadores de B para o detector de vazamento -------------------------------------------------------------------------------------


def marcadores_de_b(foto: dict, dono: Dono) -> list[str]:
    em_b: set[str] = set()
    fora: set[str] = set()
    for nome, linhas in foto.items():
        for linha in linhas.values():
            alvo = em_b if dono.de(nome, linha) == TENANT_B else fora
            for valor in linha:
                # só texto distintivo (nome, título, e-mail, id): palavras soltas de enum ("prospeccao", "linkedin") coincidem por acaso
                if isinstance(valor, str) and 12 <= len(valor) <= 160 and (" " in valor or "@" in valor or re.search(r"\d", valor)):
                    alvo.add(valor)
    # o id do tenant é identidade pública na rede (e A o envia nas rotas de conexão); códigos internos em CAIXA_ALTA@n são constantes de módulo
    return sorted(m for m in (em_b - fora) if m != TENANT_B and not re.fullmatch(r"[A-Z_]+@\d+", m))


# --- cenário --------------------------------------------------------------------------------------------------------------------------


def _licenca(db: Session, tenant_id: str) -> None:
    if db.get(Tenant, tenant_id) is None:
        db.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}"))
        db.flush()
    plano = db.query(Plano).filter_by(nome="Plano Padrão Teste").one_or_none()
    if plano is None:
        # todos os módulos: sem isso as rotas de licitações/compras/sourcing parariam no gate de plano e a lógica não seria exercitada
        plano = Plano(nome="Plano Padrão Teste", franquia_contas_mes=1000, max_usuarios=50, preco_mensal=0.0,
                      modulos_contratados=["map", "predator", "crm", "bids", "procurement", "sourcing", "sourcing_enterprise"])
        db.add(plano)
        db.flush()
    if db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none() is None:
        db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db.commit()


def _categoria_bloqueio(resposta) -> str:
    if resposta.status_code == 404:
        return "nao_encontrado"
    try:
        detalhe = str(resposta.json().get("detalhe", resposta.json().get("detail", ""))).lower()
    except Exception:  # noqa: BLE001
        detalhe = ""
    if any(t in detalhe for t in ("módulo", "modulo", "plano", "licen", "contratad")):
        return "gate_plano"
    if any(t in detalhe for t in ("super", "papel", "permiss", "somente", "só ", "exclusiv", "admin", "gestor")):
        return "gate_papel"
    return "outro"


def _resetar_limitadores() -> None:
    for limitador in (limitador_auth, limitador_ia, limitador_api, limitador_portal, limitador_demo):
        limitador.resetar()


@pytest.fixture()
def cenario(db_session, client):
    _licenca(db_session, TENANT_B)
    gestora = semente.semear(db_session, TENANT_B, datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2), 100)
    token_b = auth_service.gerar_token(gestora)
    cabecalho_b = {"Authorization": f"Bearer {token_b}"}
    # conteúdo de rede de B (post, necessidade pública)
    http_b = TestClient(app, raise_server_exceptions=False)
    http_b.post("/api/v1/rede-social/posts", data={"texto": "Segredo estratégico da empresa vítima B sobre expansão"}, headers=cabecalho_b)
    http_b.post("/api/v1/rede-social/intents", json={"categoria": "software", "titulo": "Necessidade confidencial da vítima B",
                                                     "descricao": "Descrição sensível da vítima B", "visibilidade": "conexoes"}, headers=cabecalho_b)

    _licenca(db_session, TENANT_A)
    atacante = Usuario(tenant_id=TENANT_A, nome="Atacante A", email="atacante@a.com.br", papel="admin", ativo=True)
    db_session.add(atacante)
    db_session.commit()
    token_a = auth_service.gerar_token(atacante)
    return {"gestora_b": gestora, "token_a": token_a}


def test_nenhuma_rota_autenticada_vaza_ou_altera_dados_de_outro_tenant(db_session, cenario, capsys):
    inventario = _carregar_inventario()
    contextos = [c for c in inventario.contextos_efetivos() if any(a in str(c.dependant.dependencies) for a in ("get_usuario_atual",))]
    antes = fotografar(db_session)
    dono_antes = Dono(antes)
    marcadores = marcadores_de_b(antes, dono_antes)
    from app.models.conta import Conta
    from app.models.decisor import Decisor

    conta_b = db_session.query(Conta).filter_by(tenant_id=TENANT_B).order_by(Conta.id).first()
    decisor_b = db_session.query(Decisor).filter_by(tenant_id=TENANT_B).order_by(Decisor.id).first()
    TERMOS_BUSCA[:] = [conta_b.nome, decisor_b.nome, ".demo.invalid"]
    padrao = re.compile("|".join(re.escape(m) for m in marcadores))
    entidades = Entidades(db_session)

    http = TestClient(app, raise_server_exceptions=False)
    cabecalho = {"Authorization": f"Bearer {cenario['token_a']}"}
    status_por_rota: dict[str, set[int]] = {}
    erro422: dict[str, str] = {}
    negadas_com_objeto_real: set[str] = set()
    detalhes_outro: set[str] = set()
    categorias: dict[str, int] = {}
    por_rota_gate: dict[str, set] = {}
    estatistica = {"rotas": 0, "requisicoes": 0, "sem_requisicao": [], "so_422": [], "so_bloqueadas": [], "executadas": 0, "5xx": []}
    vazamentos: list[dict] = []

    for ctx in contextos:
        metodos = [m for m in (ctx.methods or []) if m not in IGNORAR_METODOS]
        if getattr(ctx, "is_sse_stream", False) or getattr(ctx, "is_json_stream", False):
            continue
        estatistica["rotas"] += 1
        status_vistos: set[int] = set()
        for metodo in metodos:
            for variante in range(3):
                if estatistica["requisicoes"] % 20 == 0:
                    _resetar_limitadores()
                USO["real"] = USO["tinha_id"] = False
                try:
                    req = montar_requisicao(ctx, entidades, variante)
                except Exception as erro:  # noqa: BLE001 - gerador best-effort; a rota é listada como não coberta
                    estatistica["sem_requisicao"].append(f"{metodo} {ctx.path}: {type(erro).__name__}")
                    break
                if req is None:
                    break
                resposta = http.request(metodo, headers=cabecalho, **req)
                estatistica["requisicoes"] += 1
                if resposta.status_code == 422 and ("json" in req or "data" in req):
                    MODO["todos"] = True
                    try:
                        req = montar_requisicao(ctx, entidades, variante)
                        resposta = http.request(metodo, headers=cabecalho, **req)
                        estatistica["requisicoes"] += 1
                    finally:
                        MODO["todos"] = False
                status_vistos.add(resposta.status_code)
                status_por_rota.setdefault(f"{metodo} {ctx.path}", set()).add(resposta.status_code)
                if resposta.status_code == 422:
                    try:
                        erro422[f"{metodo} {ctx.path}"] = str(resposta.json().get("detail") or resposta.json())[:160]
                    except Exception:  # noqa: BLE001
                        erro422[f"{metodo} {ctx.path}"] = resposta.text[:100]
                if resposta.status_code in (401, 403, 404):
                    if USO["real"]:
                        negadas_com_objeto_real.add(ctx.path)
                    categoria = _categoria_bloqueio(resposta)
                    if categoria == "outro":
                        detalhes_outro.add(str(resposta.json().get("detalhe", ""))[:80] if "json" in resposta.headers.get("content-type", "") else "?")
                    categorias[categoria] = categorias.get(categoria, 0) + 1
                    por_rota_gate.setdefault(ctx.path, set()).add(categoria)
                if resposta.status_code >= 500:
                    estatistica["5xx"].append(f"{metodo} {ctx.path} -> {resposta.status_code}")
                if 200 <= resposta.status_code < 300:
                    corpo = resposta.text if "json" in resposta.headers.get("content-type", "") or "text" in resposta.headers.get("content-type", "") else ""
                    achado = padrao.search(corpo) if corpo else None
                    if achado and not ctx.path.startswith(ROTAS_PUBLICAS_ENTRE_ASSINANTES):
                        vazamentos.append({"rota": f"{metodo} {ctx.path}", "url": req["url"], "marcador": achado.group(0)[:80], "status": resposta.status_code})
        if status_vistos and status_vistos <= {422}:
            estatistica["so_422"].append(ctx.path)
        elif status_vistos and status_vistos <= {401, 403, 404}:
            estatistica["so_bloqueadas"].append(ctx.path)
        elif status_vistos:
            estatistica["executadas"] += 1

    depois = fotografar(db_session)
    dono_depois = Dono(depois)
    violacoes: list[str] = []
    for nome, linhas in depois.items():
        antigas = antes.get(nome, {})
        for chave, linha in linhas.items():
            if antigas.get(chave) == linha:
                continue
            situacao = "nova" if chave not in antigas else "alterada"
            tabela_dono = dono_depois.de(nome, linha)
            refs = dono_depois.referencias_a(nome, linha, TENANT_B)
            if nome in TABELAS_CRUZAMENTO_LEGITIMO:
                continue
            if tabela_dono == TENANT_B:
                violacoes.append(f"{nome}{chave} {situacao}: pertence a B")
            elif refs:
                violacoes.append(f"{nome}{chave} {situacao} (dono {tabela_dono}) referencia {refs}")
        for chave, linha in antigas.items():
            if chave not in linhas and dono_antes.de(nome, linha) == TENANT_B and nome not in TABELAS_CRUZAMENTO_LEGITIMO:
                violacoes.append(f"{nome}{chave} EXCLUÍDA (era de B)")

    with capsys.disabled():
        print("\n=== VARREDURA DE ISOLAMENTO ===")
        print({k: (len(v) if isinstance(v, list) else v) for k, v in estatistica.items()})
        print("marcadores de B:", len(marcadores))
        print("--- vazamentos em resposta:", len(vazamentos))
        for v in vazamentos[:40]:
            print("  ", v)
        print("--- violações no banco:", len(violacoes))
        for v in violacoes[:40]:
            print("  ", v)
        print("--- bloqueios por categoria:", categorias)
        so_plano = sorted(r for r, c in por_rota_gate.items() if c == {"gate_plano"})
        so_outro = sorted(r for r, c in por_rota_gate.items() if c == {"outro"})
        print("--- rotas só bloqueadas por plano/módulo:", len(so_plano), so_plano[:12])
        print("--- rotas bloqueadas por motivo não classificado:", len(so_outro), so_outro[:15])
        print("--- rotas negadas a A com objeto REAL de B (prova positiva):", len(negadas_com_objeto_real))
        print("--- amostra de motivos 'outro':", sorted(detalhes_outro)[:14])
        for rota in estatistica["so_422"]:
            for chave, texto in erro422.items():
                if chave.endswith(" " + rota):
                    print("   422>", chave, "|", texto)
        print("--- 5xx:", len(estatistica["5xx"]))
        for v in estatistica["5xx"][:25]:
            print("  ", v)
        print("--- rotas só 422 (não exercitadas):", len(estatistica["so_422"]))
        print("--- sem requisição:", len(estatistica["sem_requisicao"]))
        destino = os.environ.get("ISOLAMENTO_RELATORIO")
        if destino:
            Path(destino).write_text(
                json.dumps({"estatistica": estatistica, "vazamentos": vazamentos, "violacoes": violacoes,
                            "status_por_rota": {k: sorted(v) for k, v in status_por_rota.items()}}, ensure_ascii=False, indent=1), encoding="utf-8"
            )

    assert not vazamentos, f"dados de B apareceram em respostas entregues a A: {vazamentos[:5]}"
    assert not violacoes, f"A alterou ou referenciou dados de B: {violacoes[:5]}"


# --- Rotas que a varredura automática não consegue exercitar (corpo com regras próprias): ataques dirigidos ------------------------------


def _atacar(cenario, metodo: str, url: str, **corpo):
    http = TestClient(app, raise_server_exceptions=False)
    return http.request(metodo, url, headers={"Authorization": f"Bearer {cenario['token_a']}"}, **corpo)


def _de_b(db: Session, modelo):
    return db.query(modelo).filter_by(tenant_id=TENANT_B).order_by(modelo.id).all()


def test_atacante_nao_altera_papel_de_decisor_de_b(db_session, cenario):
    from app.models.decisor import Decisor

    decisor = _de_b(db_session, Decisor)[0]
    antes = decisor.papel_confirmado

    resposta = _atacar(cenario, "POST", f"/api/v1/contas/{decisor.conta_id}/decisores/{decisor.id}/papel", json={"papel": "DECISION_MAKER"})

    assert resposta.status_code in (403, 404), resposta.text
    db_session.expire_all()
    assert db_session.get(Decisor, decisor.id).papel_confirmado == antes


def test_atacante_nao_marca_resultado_de_reuniao_de_b(db_session, cenario):
    from app.models.reuniao import Reuniao

    reuniao = _de_b(db_session, Reuniao)[0]
    antes = reuniao.status

    resposta = _atacar(cenario, "POST", f"/api/v1/reunioes/{reuniao.id}/marcar-resultado", json={"status": "no_show"})

    assert resposta.status_code in (403, 404), resposta.text
    db_session.expire_all()
    assert db_session.get(Reuniao, reuniao.id).status == antes


def test_atacante_nao_reordena_funil_de_b(db_session, cenario):
    from app.models.estagio_funil import EstagioFunil

    estagios = _de_b(db_session, EstagioFunil)
    ordem_antes = [(e.id, e.ordem) for e in estagios]

    resposta = _atacar(cenario, "POST", "/api/v1/crm/estagios/reordenar", json={"ordem_ids": [e.id for e in reversed(estagios)]})

    assert resposta.status_code in (403, 404, 409, 422), resposta.text
    db_session.expire_all()
    assert [(e.id, e.ordem) for e in _de_b(db_session, EstagioFunil)] == ordem_antes


def test_atacante_nao_registra_interacao_em_conta_de_b(db_session, cenario):
    from app.models.conta import Conta
    from app.models.interacao_conta import InteracaoConta

    conta = _de_b(db_session, Conta)[0]
    antes = db_session.query(InteracaoConta).count()

    resposta = _atacar(cenario, "POST", "/api/v1/saude-contas/interacoes", json={"conta_id": conta.id, "tipo": "contato", "descricao": "x"})

    assert resposta.status_code in (403, 404), resposta.text
    assert db_session.query(InteracaoConta).count() == antes


def test_atacante_nao_cria_licitacao_apontando_para_conta_ou_oferta_de_b(db_session, cenario):
    from app.models.conta import Conta
    from app.models.licitacao import Licitacao
    from app.models.oferta import Oferta

    conta, oferta = _de_b(db_session, Conta)[0], _de_b(db_session, Oferta)[0]
    antes = db_session.query(Licitacao).filter_by(tenant_id=TENANT_A).count()

    resposta = _atacar(cenario, "POST", "/api/v1/bids/licitacoes", json={"titulo": "Edital de ataque", "orgao_nome": "Órgão", "conta_id": conta.id, "oferta_id": oferta.id})

    db_session.expire_all()
    criadas = db_session.query(Licitacao).filter_by(tenant_id=TENANT_A).all()
    assert not any(l.conta_id == conta.id or l.oferta_id == oferta.id for l in criadas), f"licitação de A aponta para objeto de B (status {resposta.status_code})"
    assert len(criadas) == antes or resposta.status_code in (201,)


def test_atacante_nao_declara_registro_de_oportunidade_sobre_conta_de_b(db_session, cenario):
    from app.models.conta import Conta
    from app.models.registro_oportunidade import RegistroOportunidade

    conta = _de_b(db_session, Conta)[0]

    resposta = _atacar(cenario, "POST", "/api/v1/registro-oportunidade", json={"cnpj": "11222333000181", "nome_empresa": "Alvo", "conta_id": conta.id})

    assert resposta.status_code in (403, 404), resposta.text
    assert not any(r.conta_id == conta.id for r in db_session.query(RegistroOportunidade).filter_by(tenant_id=TENANT_A))


def test_controle_positivo_o_detector_enxerga_os_dados_quando_quem_pergunta_e_o_dono(db_session, cenario):
    """Se este teste falhar, o 'zero vazamentos' da varredura não significa nada: o detector estaria cego."""
    antes = fotografar(db_session)
    marcadores = marcadores_de_b(antes, Dono(antes))
    padrao = re.compile("|".join(re.escape(m) for m in marcadores))
    token_b = auth_service.gerar_token(cenario["gestora_b"])
    http = TestClient(app, raise_server_exceptions=False)

    achados = {}
    for rota in ("/api/v1/leads/contas", "/api/v1/crm/negocios", "/api/v1/bids/licitacoes", "/api/v1/icp", "/api/v1/ofertas"):
        resposta = http.get(rota, headers={"Authorization": f"Bearer {token_b}"})
        achados[rota] = (resposta.status_code, bool(padrao.search(resposta.text)))

    assert sum(1 for status, achou in achados.values() if status == 200 and achou) >= 3, achados
