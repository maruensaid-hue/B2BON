"""Conexões do LinkedIn viram contatos e empresas no CRM.

O vendedor exporta o CSV de conexões do próprio LinkedIn (recurso oficial; nunca há login nem raspagem) e, na importação:

* cada conexão vira um CONTATO (decisor) da empresa em que trabalha, com cargo, e-mail (se o export trouxer) e o link do perfil no LinkedIn;
* cada empresa vira uma CONTA na lista de prospecção "Importação LinkedIn" do vendedor, sem duplicar: nomes iguais depois de normalizados (acento, caixa,
  sufixo jurídico) são a mesma empresa, e empresas já cadastradas no CRM são reaproveitadas;
* nomes parecidos mas diferentes (sigla, nome fantasia × razão social, "Acme" × "Acme Brasil") passam pela IA, que decide se é a mesma empresa ou apenas um
  homônimo/nome parecido SEM relação direta. Na dúvida, ou se a IA estiver indisponível, as empresas ficam separadas (nunca se junta por palpite);
* reimportar não duplica nada: contato e empresa já existentes só ganham os campos que estavam vazios.

Telefones não vêm no export do LinkedIn. Para obtê-los, a lista "Importação LinkedIn" usa a pesquisa de decisores já governada (franquia, limite por pesquisa e
decisores por empresa do perfil contratado); o que o provedor devolver para a mesma pessoa completa o contato, sem duplicar."""

import difflib
import json
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.graph.client import Neo4jClient, sincronizar_com_tolerancia
from app.llm.schemas import LLMRequest
from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.lista_prospeccao import ListaProspeccao
from app.models.usuario import Usuario
from app.contexts.intelligence import contract as intel
from app.services import auditoria_service
from app.services.errors import IAIndisponivel, RegraNegocioViolada

logger = logging.getLogger(__name__)

NOME_DA_LISTA = "Importação LinkedIn"
ORIGEM = "linkedin"
MAX_CHAMADAS_IA = 4
GRUPOS_POR_CHAMADA = 25
MAX_NOMES_POR_GRUPO = 12

_SUFIXOS_JURIDICOS = {"ltda", "ltd", "limited", "sa", "eireli", "me", "epp", "inc", "llc", "corp", "corporation", "gmbh", "plc", "cia", "sas", "srl", "ag"}
_SEM_EMPRESA = {"", "autonomo", "autonoma", "freelancer", "freelance", "self employed", "selfemployed", "independente", "consultor independente", "aposentado",
                "aposentada", "desempregado", "desempregada", "confidencial", "n a", "na", "nao informado", "none", "ninguem", "proprio", "por conta propria",
                "profissional liberal", "estudante"}
# Palavras comuns demais para dizer que duas empresas "se parecem" (só por elas ninguém é candidato a ser a mesma empresa).
_GENERICAS = {"banco", "grupo", "empresa", "servicos", "tecnologia", "tecnologias", "consultoria", "solucoes", "sistemas", "group", "company", "consulting",
              "services", "solutions", "technology", "technologies", "brasil", "brazil", "do", "da", "de", "dos", "das", "e", "the", "and", "global", "international",
              "internacional", "industria", "comercio", "holding", "participacoes", "negocios", "digital", "software", "systems", "partners", "associados"}


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def normalizar_empresa(nome: str | None) -> str:
    """Chave estável do nome da empresa: sem acento, caixa, pontuação e sufixo jurídico ('Acme Ltda.' == 'ACME')."""
    texto = re.sub(r"[^a-z0-9 ]+", " ", _sem_acentos((nome or "").lower()))
    tokens = texto.split()
    if len(tokens) > 2 and tokens[-2:] == ["s", "a"]:  # "S.A." / "S/A"
        tokens = tokens[:-2]
    while len(tokens) > 1 and tokens[-1] in _SUFIXOS_JURIDICOS:
        tokens.pop()
    return " ".join(tokens)


def _tokens_distintivos(chave: str) -> set[str]:
    return {t for t in chave.split() if len(t) >= 3 and t not in _GENERICAS}


def _normalizar_pessoa(nome: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", _sem_acentos((nome or "").lower())).split())


def _url_completa(url_normalizada: str | None) -> str | None:
    if not url_normalizada:
        return None
    return url_normalizada if url_normalizada.startswith("http") else f"https://{url_normalizada}"


def _dominio_do_email(email: str | None) -> str | None:
    if email and "@" in email:
        dominio = email.rsplit("@", 1)[1].strip().lower()
        if dominio and dominio not in {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "icloud.com", "live.com", "uol.com.br", "bol.com.br",
                                      "terra.com.br", "msn.com", "protonmail.com"}:
            return dominio
    return None


@dataclass
class _Empresa:
    chave: str
    nomes: Counter = field(default_factory=Counter)  # grafias que apareceram -> quantas conexões
    conexoes: list[ConexaoLinkedin] = field(default_factory=list)
    conta: Conta | None = None  # empresa já cadastrada no CRM

    @property
    def nome_exibicao(self) -> str:
        if self.conta is not None:
            return self.conta.nome
        return sorted(self.nomes.items(), key=lambda par: (-par[1], len(par[0]), par[0]))[0][0]

    @property
    def total(self) -> int:
        return len(self.conexoes)


# ---------------------------------------------------------------------------------------------------------------- agrupamento por IA


def _candidatos(empresas: dict[str, _Empresa]) -> list[list[str]]:
    """Grupos de chaves que PODEM ser a mesma empresa (nome parecido): quem compartilha uma palavra distintiva rara (poucas empresas a têm) ou, para palavras
    mais comuns, é subconjunto do outro nome ou muito similar. Só candidatos vão à IA; chaves sem nenhum parecido nunca são juntadas."""
    por_palavra: dict[str, list[str]] = {}
    for chave in empresas:
        for token in _tokens_distintivos(chave):
            por_palavra.setdefault(token, []).append(chave)
    pai = {chave: chave for chave in empresas}

    def achar(x: str) -> str:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for chaves in por_palavra.values():
        if len(chaves) < 2 or len(chaves) > 60:  # palavra comum demais não indica nada
            continue
        rara = len(chaves) <= 12
        for i, a in enumerate(chaves):
            for b in chaves[i + 1:]:
                ta, tb = set(a.split()), set(b.split())
                if rara or ta <= tb or tb <= ta or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
                    pai[achar(a)] = achar(b)
    grupos: dict[str, list[str]] = {}
    for chave in empresas:
        grupos.setdefault(achar(chave), []).append(chave)
    return [sorted(g, key=lambda c: (-empresas[c].total, c))[:MAX_NOMES_POR_GRUPO] for g in grupos.values() if len(g) > 1]


def _descrever(empresas: dict[str, _Empresa], grupo: list[str]) -> list[dict]:
    saida = []
    for chave in grupo:
        e = empresas[chave]
        cargos = [c.cargo_atual for c in e.conexoes if c.cargo_atual][:3]
        dominios = sorted({d for c in e.conexoes if (d := _dominio_do_email(c.email))})[:3]
        item: dict = {"nome": e.nome_exibicao, "conexoes": e.total, "cargos": cargos, "dominios_de_email": dominios}
        if e.conta is not None:
            item["ja_cadastrada_no_crm"] = True
            item["segmento"] = e.conta.segmento
            item["dominio"] = e.conta.dominio
        saida.append(item)
    return saida


_SISTEMA = (
    "Você deduplica empresas importadas das conexões do LinkedIn de um vendedor. Para cada grupo, diga quais nomes são a MESMA organização. "
    "Junte apenas variações do mesmo nome: sigla, sufixo jurídico, acento, 'Ltda', nome fantasia × razão social, grafia diferente. "
    "NÃO junte homônimos nem nomes apenas parecidos sem relação direta (empresas diferentes que partilham uma palavra, mesmo nome em países/setores "
    "diferentes, empresas de um mesmo grupo mas com atuação própria). Domínios de e-mail corporativo iguais são forte indício de mesma empresa; "
    "domínios diferentes são forte indício de empresas diferentes. Na dúvida, mantenha separadas. Responda SOMENTE com JSON."
)


def _perguntar_a_ia(db: Session, llm, tenant_id: str, usuario_id: int, lote: list[list[dict]]) -> list[list[list[int]]] | None:
    """Devolve, por grupo, as partições de índices que a IA considera a mesma empresa; None se a resposta não for utilizável."""
    nomes_json = json.dumps([{"grupo": i, "nomes": nomes} for i, nomes in enumerate(lote)], ensure_ascii=False)
    prompt = (
        "Grupos de nomes (índices começam em 0 dentro de cada grupo):\n"
        + intel.prompt_seguro.bloco_dados_externos("nomes_de_empresas_do_linkedin", nomes_json)
        + '\n\nResponda exatamente neste formato: {"grupos":[{"grupo":0,"mesmas":[[0,1],[2]]}]} — em "mesmas", cada lista interna reúne os índices que são a '
        "mesma empresa; todo índice deve aparecer uma única vez (sozinho se for uma empresa distinta)."
    )
    # Pelo AI Gateway: a chamada é medida e cobrada em créditos de IA do tenant como qualquer outra.
    resposta = intel.gerar(db, llm, intel.ContextoIA(tenant_id=tenant_id, feature="predator.unificar_empresas_linkedin", usuario_id=usuario_id),
                           LLMRequest(prompt=prompt, system=_SISTEMA, max_tokens=2000))
    achado = re.search(r"\{.*\}", resposta.content, re.DOTALL)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
        por_grupo: dict[int, list[list[int]]] = {}
        for item in dados["grupos"]:
            grupo, mesmas = int(item["grupo"]), item["mesmas"]
            total = len(lote[grupo])
            indices = [i for particao in mesmas for i in particao]
            if sorted(indices) != list(range(total)):  # índice faltando ou repetido: resposta descartada
                continue
            por_grupo[grupo] = [[int(i) for i in particao] for particao in mesmas]
        return [por_grupo.get(i, [[j] for j in range(len(lote[i]))]) for i in range(len(lote))]
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def _unir_com_ia(db: Session, empresas: dict[str, _Empresa], llm, tenant_id: str, usuario_id: int) -> dict:
    """Junta as empresas que a IA confirma serem a mesma. Devolve o resumo (`ia_disponivel`, `variacoes_unificadas`, `homonimos_mantidos_separados`)."""
    candidatos = _candidatos(empresas)
    resumo = {"ia_disponivel": True, "grupos_analisados": len(candidatos), "variacoes_unificadas": [], "homonimos_mantidos_separados": 0, "grupos_sem_analise": 0}
    if not candidatos:
        return resumo
    chamadas = 0
    for inicio in range(0, len(candidatos), GRUPOS_POR_CHAMADA):
        lote = candidatos[inicio:inicio + GRUPOS_POR_CHAMADA]
        if chamadas >= MAX_CHAMADAS_IA:
            resumo["grupos_sem_analise"] += len(lote)
            continue
        chamadas += 1
        try:
            decisoes = _perguntar_a_ia(db, llm, tenant_id, usuario_id, [_descrever(empresas, g) for g in lote])
        except (IAIndisponivel, RegraNegocioViolada) as erro:  # IA fora do ar, sem créditos de IA ou limite de uso: segue sem juntar nada
            logger.warning("LINKEDIN_IMPORTACAO_SEM_IA tenant=%s motivo=%s", tenant_id, erro)
            decisoes = None
        if decisoes is None:
            resumo["ia_disponivel"] = False
            resumo["grupos_sem_analise"] += len(lote)
            continue
        for grupo, particoes in zip(lote, decisoes, strict=True):
            for particao in particoes:
                if len(particao) < 2:
                    continue
                chaves = [grupo[i] for i in particao]
                destino = next((c for c in chaves if empresas[c].conta is not None), chaves[0])  # a empresa já cadastrada no CRM tem preferência
                nomes = [empresas[c].nome_exibicao for c in chaves]
                for chave in chaves:
                    if chave == destino:
                        continue
                    origem = empresas.pop(chave)
                    empresas[destino].nomes.update(origem.nomes)
                    empresas[destino].conexoes.extend(origem.conexoes)
                    if empresas[destino].conta is None and origem.conta is not None:
                        empresas[destino].conta = origem.conta
                resumo["variacoes_unificadas"].append({"empresa": empresas[destino].nome_exibicao, "variacoes": sorted(set(nomes))})
            if len(particoes) > 1:  # a IA manteve ao menos um nome parecido separado (homônimo ou sem relação direta)
                resumo["homonimos_mantidos_separados"] += 1
    return resumo


# --------------------------------------------------------------------------------------------------------------------- importação


def _contas_visiveis(db: Session, tenant_id: str, usuario: Usuario, restrito: bool) -> list[Conta]:
    consulta = db.query(Conta).outerjoin(ICP, ICP.id == Conta.icp_id).filter(Conta.tenant_id == tenant_id)
    if restrito:
        consulta = consulta.filter(
            ((Conta.vendedor_usuario_id == usuario.id) | (Conta.criado_por_usuario_id == usuario.id) | (ICP.criador_usuario_id == usuario.id)),
            ((Conta.vendedor_usuario_id.is_(None)) | (Conta.vendedor_usuario_id == usuario.id)),
        )
    return consulta.all()


def _lista_do_usuario(db: Session, tenant_id: str, usuario: Usuario) -> ListaProspeccao:
    lista = db.query(ListaProspeccao).filter_by(tenant_id=tenant_id, nome=NOME_DA_LISTA, criado_por_usuario_id=usuario.id).first()
    if lista is None:
        lista = ListaProspeccao(tenant_id=tenant_id, nome=NOME_DA_LISTA, icp_id=None, cargos_alvo=None, criado_por_usuario_id=usuario.id)
        db.add(lista)
        db.flush()
    return lista


def importar_como_contatos(db: Session, tenant_id: str, usuario: Usuario, conexoes: list[ConexaoLinkedin], llm, graph: Neo4jClient) -> dict:
    """Cria/atualiza empresas e contatos a partir das conexões já gravadas. Ver o docstring do módulo."""
    restrito = usuario.papel == "user"
    ator_id = str(usuario.id)
    lista = _lista_do_usuario(db, tenant_id, usuario)

    empresas: dict[str, _Empresa] = {}
    sem_empresa = 0
    for conexao in conexoes:
        chave = normalizar_empresa(conexao.empresa_atual)
        if chave in _SEM_EMPRESA or not conexao.empresa_atual:
            sem_empresa += 1
            continue
        empresa = empresas.setdefault(chave, _Empresa(chave=chave))
        empresa.nomes[conexao.empresa_atual.strip()] += 1
        empresa.conexoes.append(conexao)

    # Empresas já cadastradas no CRM (visíveis ao usuário): mesmo nome normalizado = mesma empresa; nome parecido vai para a IA junto com as importadas.
    existentes: dict[str, Conta] = {}
    for conta in _contas_visiveis(db, tenant_id, usuario, restrito):
        existentes.setdefault(normalizar_empresa(conta.nome), conta)
    for chave, conta in existentes.items():
        if chave in empresas:
            empresas[chave].conta = conta
    nos_para_ia = dict(empresas)
    tokens_importados = set().union(*(_tokens_distintivos(c) for c in empresas)) if empresas else set()
    for chave, conta in existentes.items():
        if chave not in nos_para_ia and _tokens_distintivos(chave) & tokens_importados:
            nos_para_ia[chave] = _Empresa(chave=chave, nomes=Counter({conta.nome: 1}), conta=conta)
    resumo_ia = _unir_com_ia(db, nos_para_ia, llm, tenant_id, usuario.id)
    # `_unir_com_ia` só mexe em `nos_para_ia`: devolve ao dicionário das importadas o que foi unido, e descarta cadastros do CRM sem conexão.
    empresas = {chave: e for chave, e in nos_para_ia.items() if e.conexoes}

    decisores_por_conta: dict[int, list[Decisor]] = {}
    ids_existentes = [e.conta.id for e in empresas.values() if e.conta is not None]
    if ids_existentes:
        for d in db.query(Decisor).filter(Decisor.tenant_id == tenant_id, Decisor.conta_id.in_(ids_existentes)).all():
            decisores_por_conta.setdefault(d.conta_id, []).append(d)

    contas_criadas = contas_reaproveitadas = contatos_criados = contatos_atualizados = com_email = 0
    for empresa in sorted(empresas.values(), key=lambda e: e.nome_exibicao.lower()):
        conta = empresa.conta
        if conta is None:
            conta = Conta(
                tenant_id=tenant_id, icp_id=None, lista_prospeccao_id=lista.id, nome=empresa.nome_exibicao, status="prospectada", origem=ORIGEM,
                criado_por_usuario_id=usuario.id if restrito else None, vendedor_usuario_id=usuario.id if restrito else None,
            )
            db.add(conta)
            db.flush()
            if sincronizar_com_tolerancia(
                lambda: graph.upsert_conta(tenant_id, conta.id, {"nome": conta.nome, "cnpj": conta.cnpj}),  # noqa: B023 — roda na mesma iteração
                "conta", conta.id,
            ):
                conta.neo4j_node_id = str(conta.id)
            contas_criadas += 1
        else:
            contas_reaproveitadas += 1
            if conta.lista_prospeccao_id is None:  # empresa avulsa passa a aparecer na fila; quem já está em outra lista continua nela
                conta.lista_prospeccao_id = lista.id
        existentes_da_conta = decisores_por_conta.setdefault(conta.id, [])
        for conexao in empresa.conexoes:
            nome_pessoa, url = _normalizar_pessoa(conexao.nome_completo), _url_completa(conexao.url_perfil)
            email = (conexao.email or "").strip().lower() or None
            igual = next((
                d for d in existentes_da_conta
                if _normalizar_pessoa(d.nome) == nome_pessoa or (email and d.email and d.email.strip().lower() == email)
                or (url and d.linkedin_url and _url_completa(_normalizar_url(d.linkedin_url)) == url)
            ), None)
            if igual is not None:
                alterou = False
                for campo, valor in (("cargo", conexao.cargo_atual), ("email", conexao.email), ("linkedin_url", url)):
                    if valor and not getattr(igual, campo):
                        setattr(igual, campo, valor)
                        alterou = True
                if alterou:
                    contatos_atualizados += 1
                continue
            decisor = Decisor(
                tenant_id=tenant_id, conta_id=conta.id, nome=conexao.nome_completo, cargo=conexao.cargo_atual, email=conexao.email, linkedin_url=url,
                canal_provavel="email" if conexao.email else "linkedin", origem=ORIGEM, criado_por_usuario_id=usuario.id if restrito else None,
            )
            db.add(decisor)
            existentes_da_conta.append(decisor)
            contatos_criados += 1
            com_email += 1 if conexao.email else 0

    auditoria_service.registrar(
        db, tenant_id, "linkedin_conexoes_importadas_como_contatos", "lista_prospeccao", lista.id, ator_id,
        {"contas_criadas": contas_criadas, "contas_reaproveitadas": contas_reaproveitadas, "contatos_criados": contatos_criados,
         "contatos_atualizados": contatos_atualizados, "ia_disponivel": resumo_ia["ia_disponivel"]},
    )
    db.commit()
    return {
        "lista_id": lista.id, "lista_nome": lista.nome, "contas_criadas": contas_criadas, "contas_reaproveitadas": contas_reaproveitadas,
        "contatos_criados": contatos_criados, "contatos_atualizados": contatos_atualizados, "contatos_com_email": com_email,
        "conexoes_sem_empresa": sem_empresa, **resumo_ia,
    }


def _normalizar_url(url: str) -> str | None:
    from app.services.linkedin_conexao_service import _normalizar_url_perfil  # import tardio: aquele módulo chama este

    return _normalizar_url_perfil(url)
