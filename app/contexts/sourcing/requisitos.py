"""Requirement Engine (S1, D-055): um extrator para edital, TR, ETP, RFP,
RFI, RFQ, questionário de fornecedor e especificação técnica.

O que muda por tipo de documento é o **perfil** (instrução, categorias,
tamanho do bloco). O laço é um só: blocos de páginas → IA via Gateway (uma
execução de crédito por documento) → cada item só entra se a citação estiver
literalmente no texto; a página é calculada pelo sistema e a cláusula só vale
se aparecer na página (D-031). Quem chama decide onde gravar.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.contexts.intelligence.contract import ContextoIA, execucao, gerar, prompt_seguro
from app.contexts.shared import grounding
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest


@dataclass(frozen=True)
class PerfilExtracao:
    nome: str
    sistema: str
    categorias: tuple[str, ...]
    max_tokens: int
    caracteres_por_bloco: int = grounding.CARACTERES_POR_BLOCO
    maximo_blocos: int = 8
    maximo_itens_por_bloco: int = 60


@dataclass(frozen=True)
class ItemExtraido:
    categoria: str
    descricao: str
    evidencia: str
    pagina: int
    clausula: str | None


@dataclass(frozen=True)
class Extracao:
    itens: list[ItemExtraido]
    sem_evidencia: int
    blocos_analisados: int
    paginas_analisadas: int
    paginas_total: int
    parcial: bool


def extrair(db: Session, llm: LLMProvider, contexto: ContextoIA, paginas: list[str], perfil: PerfilExtracao,
            rotulo_fonte: str, confirmado: bool = False) -> Extracao:
    todos = grounding.blocos(paginas, perfil.caracteres_por_bloco)
    blocos = todos[:perfil.maximo_blocos]
    # Fase 15: um documento = uma execução de crédito, por mais blocos que tenha.
    with execucao(db, contexto, parametros={"paginas": len(paginas)}, confirmado=confirmado) as ctx:
        respostas = [
            (bloco, gerar(db, llm, ctx, LLMRequest(
                system=perfil.sistema,
                prompt=prompt_seguro.bloco_dados_externos(rotulo_fonte, grounding.corpo_do_bloco(paginas, bloco)),
                max_tokens=perfil.max_tokens,
            )))
            for bloco in blocos
        ]
    itens: list[ItemExtraido] = []
    sem_evidencia = 0
    for bloco, resposta in respostas:
        for item in grounding.itens_json(resposta.content)[:perfil.maximo_itens_por_bloco]:
            descricao = str(item.get("descricao") or "").strip()[:500]
            citacao = str(item.get("citacao") or "").strip()[:2000]
            categoria = str(item.get("categoria") or "").strip().upper()
            if not descricao or categoria not in perfil.categorias:
                continue
            pagina = grounding.ancorar(paginas, bloco, citacao)
            if pagina is None:
                sem_evidencia += 1
                continue
            itens.append(ItemExtraido(categoria, descricao, citacao, pagina,
                                      grounding.clausula_valida(item.get("clausula"), paginas[pagina - 1])))
    return Extracao(itens, sem_evidencia, len(blocos), sum(len(b) for b in blocos), len(paginas), len(todos) > perfil.maximo_blocos)
