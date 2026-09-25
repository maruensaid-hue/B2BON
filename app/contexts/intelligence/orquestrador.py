"""B2B ON Intelligence Agent — orquestração de agentes (Fase 12).

Uma pergunta em linguagem natural → um agente especialista → uma ferramenta.

- Ferramentas são registradas pelos próprios contextos (`registrar`); este
  módulo não importa nenhum contexto de negócio (a barreira Buy/Sell
  continua estrutural: o lado comprador registra as dele de dentro dele).
- Roteamento determinístico primeiro (palavras-chave, custo zero). Sem
  rota, cai para a IA (feature `intelligence.orquestrador`, C1, medida), que
  só enxerga as ferramentas que ESTE usuário pode usar.
- Permissões, nesta ordem: ferramenta declarada no registro; agente
  autorizado a usá-la; módulo do plano; papel do usuário; sensibilidade.
  READ executa. WRITE e EXTERNAL_ACTION viram proposta para confirmação
  humana (nunca executam aqui). SENSITIVE_ACTION é recusada sempre.
- O tenant vem sempre do usuário autenticado, nunca dos parâmetros.
- Compra (BUY) e venda (SELL) não se misturam: se a pergunta serve aos
  dois lados, o agente pergunta de qual lado se trata.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence import registro
from app.contexts.intelligence.gateway import ContextoIA, gerar
from app.contexts.shared.ferramentas import ContextoFerramenta, FerramentaExecutavel, Parametro, registradas, registrar
from app.contexts.shared.texto import normalizar, termos

__all__ = ["ContextoFerramenta", "FerramentaExecutavel", "Parametro", "catalogo", "perguntar", "registrar"]
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest

AGENTE_ORQUESTRADOR = "b2bon_intelligence_agent"
FEATURE = "intelligence.orquestrador"
# Palavras inteiras (sem radical nem stopword: "clientes" é stopword do casamento
# por termos, e o radical "contrat-" casaria com "contratos" e falsearia o lado).
_DICAS_COMPRA = frozenset("fornecedor fornecedores compra compras comprar pca".split())
_DICAS_VENDA = frozenset("cliente clientes venda vendas vendemos ganhamos licitacao licitacoes edital proposta".split())


def validar(ferramenta: FerramentaExecutavel) -> str | None:
    """Coerência com o registro declarado; ferramenta inválida nunca é oferecida."""
    declarada = registro.FERRAMENTAS.get(ferramenta.nome)
    if declarada is None:
        return "não declarada em registro.FERRAMENTAS"
    if declarada.sensibilidade == registro.Sensibilidade.READ and ferramenta.executar is None:
        return "ferramenta READ sem função"
    if declarada.sensibilidade != registro.Sensibilidade.READ and ferramenta.executar is not None:
        return f"{declarada.sensibilidade} não pode ter execução automática"
    if ferramenta.lado not in ("SELL", "BUY", "NEUTRO"):
        return "lado inválido"
    return None


def ferramentas_registradas() -> dict[str, FerramentaExecutavel]:
    return {nome: f for nome, f in registradas().items() if validar(f) is None}


def _termos_chave(ferramenta: FerramentaExecutavel) -> set[str]:
    return {t for p in ferramenta.palavras_chave for t in termos(p)}


def _modulos(nome: str) -> tuple[str, ...]:
    modulo = registro.FERRAMENTAS[nome].modulo
    return tuple(m.strip() for m in modulo.split("|")) if modulo else ()


def motivo_bloqueio(ferramenta: FerramentaExecutavel, ctx: ContextoFerramenta, tem_modulo: Callable[[str], bool]) -> str | None:
    if not registro.agente_pode_usar(ferramenta.agente, ferramenta.nome):
        return f"o agente {ferramenta.agente} não está autorizado a usar {ferramenta.nome}"
    modulos = [m for m in _modulos(ferramenta.nome) if m not in ("", "intelligence", "plataforma")]
    if modulos and not any(tem_modulo(m) for m in modulos):
        return "módulo não contratado no plano"
    if ferramenta.papeis is not None and ctx.papel not in ferramenta.papeis:
        return "seu papel não permite esta ferramenta"
    return None


def permitidas(ctx: ContextoFerramenta, tem_modulo: Callable[[str], bool]) -> list[FerramentaExecutavel]:
    return [f for f in ferramentas_registradas().values() if motivo_bloqueio(f, ctx, tem_modulo) is None]


def _extrair(ferramenta: FerramentaExecutavel, pergunta: str) -> tuple[dict, list[str]]:
    valores, faltando = {}, []
    for p in ferramenta.parametros:
        if p.padrao is None:
            valores[p.nome] = pergunta
            continue
        achado = re.search(p.padrao, pergunta, re.IGNORECASE)
        if achado:
            valores[p.nome] = int(achado.group(1)) if achado.group(1).isdigit() else achado.group(1)
        elif p.obrigatorio:
            faltando.append(p.nome)
    return valores, faltando


def _rotear(pergunta: str, candidatas: list[FerramentaExecutavel]) -> tuple[list[FerramentaExecutavel], int]:
    termos_pergunta = termos(pergunta)
    pontuadas = [(len(termos_pergunta & _termos_chave(f)), f) for f in candidatas]
    melhor = max((p for p, _ in pontuadas), default=0)
    if melhor == 0:
        return [], 0
    return [f for p, f in pontuadas if p == melhor], melhor


def _rotear_com_ia(db: Session, llm: LLMProvider, ctx: ContextoFerramenta, pergunta: str, candidatas: list[FerramentaExecutavel]) -> tuple[str | None, dict]:
    catalogo = [
        {"ferramenta": f.nome, "descricao": registro.FERRAMENTAS[f.nome].descricao,
         "parametros": [p.nome for p in f.parametros if p.padrao is not None]}
        for f in candidatas
    ]
    resposta = gerar(
        db, llm, ContextoIA(tenant_id=ctx.tenant_id, feature=FEATURE, usuario_id=ctx.usuario_id),
        LLMRequest(
            system=("Você escolhe UMA ferramenta para responder à pergunta de um usuário de uma plataforma B2B. "
                    'Responda só com JSON {"ferramenta": nome ou null, "parametros": {...}}. Use apenas ferramentas do catálogo.'),
            prompt=f"Catálogo: {json.dumps(catalogo, ensure_ascii=False)}\nPergunta: {pergunta}",
            max_tokens=300,
        ),
    )
    achado = re.search(r"\{.*\}", resposta.content, re.DOTALL)
    try:
        escolha = json.loads(achado.group(0)) if achado else {}
    except json.JSONDecodeError:
        escolha = {}
    nome = escolha.get("ferramenta") if isinstance(escolha, dict) else None
    parametros = escolha.get("parametros") if isinstance(escolha, dict) and isinstance(escolha.get("parametros"), dict) else {}
    return (nome if nome in {f.nome for f in candidatas} else None), parametros


def perguntar(
    db: Session, llm: LLMProvider | None, ctx: ContextoFerramenta, pergunta: str, tem_modulo: Callable[[str], bool],
) -> dict:
    agora = datetime.now(UTC)
    passos: list[dict] = []
    candidatas = permitidas(ctx, tem_modulo)
    passos.append({"passo": "ferramentas_permitidas", "quantidade": len(candidatas)})
    escolhidas, pontos = _rotear(pergunta, candidatas)
    via = "palavras_chave"
    parametros_ia: dict = {}

    if len(escolhidas) > 1:
        lados = {f.lado for f in escolhidas}
        if {"BUY", "SELL"} <= lados:
            dicas = set(normalizar(pergunta).split())
            if dicas & _DICAS_COMPRA and not dicas & _DICAS_VENDA:
                escolhidas = [f for f in escolhidas if f.lado != "SELL"]
            elif dicas & _DICAS_VENDA and not dicas & _DICAS_COMPRA:
                escolhidas = [f for f in escolhidas if f.lado != "BUY"]
            else:
                return _resposta(agora, "ESCLARECER", None, None, via,
                                 "Esta pergunta serve tanto para compras quanto para vendas. É sobre contratos com fornecedores "
                                 "(compras) ou com clientes (vendas)?", passos, opcoes=[f.nome for f in escolhidas])
        escolhidas = escolhidas[:1]

    if not escolhidas and llm is not None and candidatas:
        via = "ia"
        nome, parametros_ia = _rotear_com_ia(db, llm, ctx, pergunta, candidatas)
        escolhidas = [f for f in candidatas if f.nome == nome]
    if not escolhidas:
        return _resposta(agora, "SEM_FERRAMENTA", None, None, via,
                         "Nenhuma ferramenta disponível no seu plano e perfil responde a esta pergunta.", passos,
                         exemplos=[f.exemplo for f in candidatas if f.exemplo])

    ferramenta = escolhidas[0]
    passos.append({"passo": "roteamento", "via": via, "ferramenta": ferramenta.nome, "agente": ferramenta.agente, "pontos": pontos})
    sensibilidade = registro.FERRAMENTAS[ferramenta.nome].sensibilidade
    if sensibilidade == registro.Sensibilidade.SENSITIVE_ACTION:
        return _resposta(agora, "RECUSADO", ferramenta, None, via,
                         "Esta ação é sensível e nunca é executada por agente. Faça-a pela tela correspondente.", passos)

    valores, faltando = _extrair(ferramenta, pergunta)
    for chave, valor in parametros_ia.items():
        if chave in {p.nome for p in ferramenta.parametros} and chave not in valores:
            valores[chave] = valor
            faltando = [f for f in faltando if f != chave]
    if faltando:
        return _resposta(agora, "FALTAM_PARAMETROS", ferramenta, None, via,
                         f"Para isso preciso de: {', '.join(faltando)}.", passos, faltando=faltando)

    if sensibilidade in (registro.Sensibilidade.WRITE, registro.Sensibilidade.EXTERNAL_ACTION):
        return _resposta(agora, "PROPOSTA_REQUER_CONFIRMACAO", ferramenta, {"parametros": valores}, via,
                         "Posso preparar esta ação, mas ela só acontece com a sua confirmação na tela correspondente"
                         + (" e passa pela fila de aprovação." if sensibilidade == registro.Sensibilidade.EXTERNAL_ACTION else "."),
                         passos)

    resultado = ferramenta.executar(db, ctx, valores)
    passos.append({"passo": "execucao", "ferramenta": ferramenta.nome})
    return _resposta(agora, "OK", ferramenta, resultado, via, resultado.get("resumo", ""), passos)


def _resposta(agora, status, ferramenta, resultado, via, texto, passos, **extra) -> dict:
    return {
        "status": status,
        "agente_orquestrador": AGENTE_ORQUESTRADOR,
        "agente": ferramenta.agente if ferramenta else None,
        "ferramenta": ferramenta.nome if ferramenta else None,
        "sensibilidade": registro.FERRAMENTAS[ferramenta.nome].sensibilidade.value if ferramenta else None,
        "roteamento": via,
        "resposta": texto,
        "resultado": resultado,
        "passos": passos,
        "gerado_em": agora,
        **extra,
    }


def catalogo(ctx: ContextoFerramenta, tem_modulo: Callable[[str], bool]) -> list[dict]:
    return [
        {"ferramenta": f.nome, "agente": f.agente, "lado": f.lado, "sensibilidade": registro.FERRAMENTAS[f.nome].sensibilidade.value,
         "descricao": registro.FERRAMENTAS[f.nome].descricao, "exemplo": f.exemplo}
        for f in permitidas(ctx, tem_modulo)
    ]
