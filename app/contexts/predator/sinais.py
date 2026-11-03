"""Sinais de conta do PREDATOR: o que se sabe de cada empresa como FATO com evidência, e a coorte como consulta sobre esses fatos.

* Catálogo governado (`CATALOGO`): só códigos daqui são gravados; código desconhecido é erro, nunca sinal inventado por digitação.
* Gravação determinística (sem IA) a partir do que o enriquecimento JÁ coleta: confirmação do domínio, páginas do site, indicadores
  financeiros publicados e o cadastro público do CNPJ. Nada aqui custa crédito.
* Critérios no ICP (`ICP.criterios_sinais`): "exigir", "excluir" e "faixa". Uma conta entra na coorte quando atende a todos; cada
  resultado diz por quê, para a lista ter um motivo e a mensagem poder citá-lo.
* `fatos_para_prompt`: os sinais que podem ser ditos a um decisor, em frases curtas, para a cadência citar um fato real em vez de
  escrever só a partir do perfil do ICP.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Query, Session

from app.contexts.predator import inteligencia_site, sinais_html
from app.models.conta import Conta
from app.models.sinal_conta import SinalConta
from app.services.errors import ValidacaoFalhou

# tipo: bool | num | texto. `na_mensagem`: pode ser citado a um decisor (capital social e situação cadastral, por exemplo, não).
CATALOGO: dict[str, dict] = {
    "DOMINIO_CONFIRMADO": {
        "rotulo": "Site confirmado como da empresa", "tipo": "bool", "fonte": "verificacao_dominio", "na_mensagem": False,
        "descricao": "O site bate com o CNPJ por evidência (CNPJ exibido, e-mail, endereço ou telefone do cadastro), ou foi confirmado à mão.",
    },
    "PAGINA_VAGAS": {
        "rotulo": "Publica página de vagas", "tipo": "bool", "fonte": "pesquisa_no_site", "na_mensagem": True,
        "descricao": "O site tem uma página de vagas, carreiras ou trabalhe conosco com conteúdo próprio: sinal de contratação.",
    },
    "PAGINA_RI": {
        "rotulo": "Tem área de Relações com Investidores", "tipo": "bool", "fonte": "pesquisa_no_site", "na_mensagem": True,
        "descricao": "O site tem página de investidores ou resultados: empresa com governança e dados públicos.",
    },
    "PUBLICA_PRIVACIDADE_LGPD": {
        "rotulo": "Publica política de privacidade/LGPD", "tipo": "bool", "fonte": "pesquisa_no_site", "na_mensagem": True,
        "descricao": "Alguma página coletada fala de LGPD, encarregado (DPO) ou política de privacidade.",
    },
    "RECEITA_LIQUIDA_PUBLICADA": {
        "rotulo": "Receita líquida publicada (R$)", "tipo": "num", "fonte": "indicadores_site", "na_mensagem": True,
        "descricao": "Receita líquida escrita no próprio site, em reais, do período mais recente encontrado.",
    },
    "IDADE_ANOS": {
        "rotulo": "Anos desde a abertura", "tipo": "num", "fonte": "cadastro_publico_cnpj", "na_mensagem": True,
        "descricao": "Anos completos desde o início de atividade no cadastro público do CNPJ.",
    },
    "CAPITAL_SOCIAL": {
        "rotulo": "Capital social (R$)", "tipo": "num", "fonte": "cadastro_publico_cnpj", "na_mensagem": False,
        "descricao": "Capital social declarado no cadastro público do CNPJ.",
    },
    "QTD_SOCIOS": {
        "rotulo": "Quantidade de sócios/administradores", "tipo": "num", "fonte": "cadastro_publico_cnpj", "na_mensagem": False,
        "descricao": "Pessoas no quadro de sócios e administradores (QSA) do cadastro público.",
    },
    "OPTANTE_SIMPLES": {
        "rotulo": "Optante pelo Simples Nacional", "tipo": "bool", "fonte": "cadastro_publico_cnpj", "na_mensagem": False,
        "descricao": "Opção pelo Simples Nacional informada no cadastro público.",
    },
    "SITUACAO_CADASTRAL": {
        "rotulo": "Situação cadastral", "tipo": "texto", "fonte": "cadastro_publico_cnpj", "na_mensagem": False,
        "descricao": "Situação do CNPJ na Receita (ATIVA, BAIXADA, INAPTA...).",
    },
    # --- Lidos no HTML da home (`sinais_html`) ---
    "ANUNCIA_GOOGLE_ADS": {
        "rotulo": "Anuncia no Google (tag de conversão)", "tipo": "bool", "fonte": "html_site", "na_mensagem": True,
        "descricao": "A home carrega a tag de conversão do Google Ads: a empresa investe em aquisição hoje.",
    },
    "ANUNCIA_META_ADS": {
        "rotulo": "Anuncia na Meta (pixel)", "tipo": "bool", "fonte": "html_site", "na_mensagem": True,
        "descricao": "A home carrega o pixel da Meta (Facebook/Instagram): investimento em anúncio.",
    },
    "TEM_SCHEMA_ORG": {
        "rotulo": "Tem dados estruturados (schema.org)", "tipo": "bool", "fonte": "html_site", "na_mensagem": False,
        "descricao": "A home publica dados estruturados para buscadores. Ausência é uma lacuna de SEO concreta.",
    },
    "WHATSAPP_NO_SITE": {
        "rotulo": "Botão de WhatsApp no site", "tipo": "bool", "fonte": "html_site", "na_mensagem": False,
        "descricao": "A home tem link de conversa por WhatsApp.",
    },
    "AGENDAMENTO_ONLINE": {
        "rotulo": "Agendamento online", "tipo": "bool", "fonte": "html_site", "na_mensagem": False,
        "descricao": "A home leva a uma agenda online (Calendly, Doctoralia...). Sem ela, o contato depende de telefone.",
    },
    "TECNOLOGIA_SITE": {
        "rotulo": "Plataformas do site", "tipo": "texto", "fonte": "html_site", "na_mensagem": False,
        "descricao": "Plataformas reconhecidas por marcas inconfundíveis no HTML (WordPress, VTEX, Nuvemshop, RD Station...). Critério 'exigir' compara o texto inteiro.",
    },
    "VAGAS_EM_PLATAFORMA": {
        "rotulo": "Vagas em plataforma de recrutamento", "tipo": "bool", "fonte": "html_site", "na_mensagem": True,
        "descricao": "A home leva a um quadro de vagas (Gupy, Solides, Kenoby...). O nome da plataforma fica no texto do sinal.",
    },
    "AGENCIA_NO_RODAPE": {
        "rotulo": "Agência creditada no rodapé", "tipo": "texto", "fonte": "html_site", "na_mensagem": False,
        "descricao": "Quem fez o site, pelo crédito do rodapé ('desenvolvido por'). Crédito sem rótulo não é registrado.",
    },
    # --- Descoberta por busca de mapa (`descoberta`) ---
    "POSICAO_MAPA": {
        "rotulo": "Posição na busca de mapa", "tipo": "num", "fonte": "descoberta_busca", "na_mensagem": False,
        "descricao": "Onde a empresa apareceu na busca de mapa pelo termo e cidade guardados no sinal. Fora do top 3 = fora do destaque que a maioria vê.",
    },
    "NOTA_AVALIACOES": {
        "rotulo": "Nota média nas avaliações", "tipo": "num", "fonte": "descoberta_busca", "na_mensagem": False,
        "descricao": "Nota média (0 a 5) da ficha da empresa no mapa.",
    },
    "QTD_AVALIACOES": {
        "rotulo": "Quantidade de avaliações", "tipo": "num", "fonte": "descoberta_busca", "na_mensagem": False,
        "descricao": "Quantas avaliações a ficha da empresa tem no mapa.",
    },
    "SEM_SITE": {
        "rotulo": "Sem site próprio", "tipo": "bool", "fonte": "descoberta_busca", "na_mensagem": False,
        "descricao": "A ficha no mapa tem nome e telefone, mas nenhum site (ou só rede social/diretório).",
    },
}

# Códigos que só existem quando achados no HTML: lida a home sem eles, o valor anterior deixa de valer (a vaga fechou, a agência mudou).
_HTML_SO_QUANDO_ACHADO = ("TECNOLOGIA_SITE", "VAGAS_EM_PLATAFORMA", "AGENCIA_NO_RODAPE")

REGRAS = ("exigir", "excluir", "faixa")


# --- Gravação -------------------------------------------------------------------------------------------------------------

def _gravar(db: Session, tenant_id: str, conta_id: int, codigo: str, *, num: float | None = None, texto: str | None = None,
            confianca: float, fonte: str, url: str | None = None, trecho: str | None = None, coleta_id: int | None = None,
            agora: datetime) -> SinalConta:
    if codigo not in CATALOGO:
        raise ValueError(f"sinal fora do catálogo: {codigo}")
    for anterior in db.query(SinalConta).filter_by(tenant_id=tenant_id, conta_id=conta_id, codigo=codigo, vigente=True):
        anterior.vigente = False
    sinal = SinalConta(
        tenant_id=tenant_id, conta_id=conta_id, codigo=codigo, valor_num=num, valor_texto=texto, confianca=confianca, fonte=fonte,
        url_evidencia=url, trecho=(trecho or None) and trecho[:500], coleta_id=coleta_id, vigente=True, observado_em=agora,
    )
    db.add(sinal)
    return sinal


_CAMINHO_VAGAS = re.compile(r"/(vagas?|carreiras?|trabalhe-conosco|jobs?|careers?|oportunidades)(/|$)", re.IGNORECASE)
_TEXTO_VAGAS = re.compile(r"\b(vagas?|carreiras?|trabalhe conosco|oportunidades? de trabalho|processo seletivo|candidat[ea]-se)\b", re.IGNORECASE)
_CAMINHO_RI = re.compile(r"/(ri|investidores|relacao-com-investidores|resultados)(/|$)", re.IGNORECASE)
_TEXTO_RI = re.compile(r"\b(rela[cç][aã]o com (os )?investidores|central de resultados|demonstra[cç][oõ]es financeiras|release de resultados)\b", re.IGNORECASE)
_TEXTO_LGPD = re.compile(r"\b(lgpd|lei geral de prote[cç][aã]o de dados|encarregad[oa] (de|pelo tratamento de) dados|dpo|pol[ií]tica de privacidade)\b", re.IGNORECASE)


def _pagina_propria(url: str, texto: str, texto_home: str, caminho: re.Pattern, conteudo: re.Pattern) -> bool:
    """Caminho do tipo certo E conteúdo próprio: site de página única devolve a home para qualquer caminho, o que não é evidência."""
    return bool(caminho.search(url)) and texto.strip() != texto_home.strip() and bool(conteudo.search(texto))


def _trecho(texto: str, padrao: re.Pattern) -> str | None:
    achado = padrao.search(texto)
    if not achado:
        return None
    return re.sub(r"\s+", " ", texto[max(0, achado.start() - 80): achado.end() + 120]).strip()


def registrar_da_coleta(db: Session, tenant_id: str, conta_id: int, coleta_id: int, paginas: list[tuple[str, str]], situacao_dominio: str,
                        indicadores: list[inteligencia_site.IndicadorExtraido], agora: datetime) -> list[SinalConta]:
    """Sinais de uma coleta do site. Domínio divergente (o site é de outra empresa) só registra que o domínio não foi confirmado."""
    confirmado = situacao_dominio in ("confirmado", "confirmado_manualmente")
    sinais = [_gravar(db, tenant_id, conta_id, "DOMINIO_CONFIRMADO", num=1 if confirmado else 0, confianca=1.0,
                      fonte="verificacao_dominio", texto=situacao_dominio, coleta_id=coleta_id, agora=agora)]
    if situacao_dominio == "divergente" or not paginas:
        return sinais
    # Domínio só provável: o fato pode ser de outra empresa, por isso vale menos.
    peso = 1.0 if confirmado else 0.6
    texto_home = paginas[0][1]

    def pagina(codigo: str, caminho: re.Pattern, conteudo: re.Pattern) -> None:
        achada = next(((u, t) for u, t in paginas[1:] if _pagina_propria(u, t, texto_home, caminho, conteudo)), None)
        sinais.append(_gravar(
            db, tenant_id, conta_id, codigo, num=1 if achada else 0, confianca=round((0.9 if achada else 0.6) * peso, 2),
            fonte="pesquisa_no_site", url=achada[0] if achada else None, trecho=_trecho(achada[1], conteudo) if achada else None,
            coleta_id=coleta_id, agora=agora,
        ))

    pagina("PAGINA_VAGAS", _CAMINHO_VAGAS, _TEXTO_VAGAS)
    pagina("PAGINA_RI", _CAMINHO_RI, _TEXTO_RI)

    lgpd = next(((u, t) for u, t in paginas if _TEXTO_LGPD.search(t)), None)
    sinais.append(_gravar(
        db, tenant_id, conta_id, "PUBLICA_PRIVACIDADE_LGPD", num=1 if lgpd else 0, confianca=round((0.85 if lgpd else 0.5) * peso, 2),
        fonte="pesquisa_no_site", url=lgpd[0] if lgpd else None, trecho=_trecho(lgpd[1], _TEXTO_LGPD) if lgpd else None,
        coleta_id=coleta_id, agora=agora,
    ))

    receita = _receita_mais_recente(indicadores)
    if receita is not None:
        valor, ind = receita
        sinais.append(_gravar(
            db, tenant_id, conta_id, "RECEITA_LIQUIDA_PUBLICADA", num=valor, texto=ind.periodo,
            confianca=round((0.9 if ind.confianca == "alta" else 0.6) * peso, 2), fonte="indicadores_site", url=ind.url,
            trecho=ind.trecho, coleta_id=coleta_id, agora=agora,
        ))
    return sinais


def _receita_mais_recente(indicadores: list[inteligencia_site.IndicadorExtraido]) -> tuple[float, inteligencia_site.IndicadorExtraido] | None:
    """Receita líquida publicada em reais (o extrator já devolve o valor em unidades), do período mais recente; período não identificado só
    vale se não houver outro."""
    candidatos = [i for i in indicadores if i.nome == "receita_liquida" and i.tipo == "publicado" and i.moeda == "BRL"]
    if not candidatos:
        return None
    escolhido = max(candidatos, key=lambda i: (i.periodo is not None, i.periodo or ""))
    return escolhido.valor, escolhido


def registrar_do_html(db: Session, tenant_id: str, conta_id: int, coleta_id: int | None, html: str, dominio: str, situacao_dominio: str,
                      agora: datetime) -> list[SinalConta]:
    """Sinais técnicos da home (pixel, plataforma, vagas, agência). Domínio divergente não registra nada: o HTML é de outra empresa."""
    if situacao_dominio == "divergente" or not html:
        return []
    peso = 1.0 if situacao_dominio in ("confirmado", "confirmado_manualmente") else 0.6
    achados = sinais_html.extrair(html, dominio)
    gravados = [
        _gravar(db, tenant_id, conta_id, a.codigo, num=a.num, texto=a.texto, confianca=round(a.confianca * peso, 2), fonte="html_site",
                url=a.url, trecho=a.trecho, coleta_id=coleta_id, agora=agora)
        for a in achados
    ]
    achados_codigos = {a.codigo for a in achados}
    for codigo in _HTML_SO_QUANDO_ACHADO:
        if codigo not in achados_codigos:
            for anterior in db.query(SinalConta).filter_by(tenant_id=tenant_id, conta_id=conta_id, codigo=codigo, vigente=True):
                anterior.vigente = False
    return gravados


def _anos_desde(data_texto: str | None, hoje: date) -> int | None:
    try:
        inicio = date.fromisoformat((data_texto or "")[:10])
    except ValueError:
        return None
    return hoje.year - inicio.year - ((hoje.month, hoje.day) < (inicio.month, inicio.day))


def registrar_do_cadastro(db: Session, tenant_id: str, conta_id: int, registro: dict | None, agora: datetime) -> list[SinalConta]:
    """Sinais do cadastro público do CNPJ (formato da BrasilAPI). Campo ausente não vira sinal."""
    if not registro:
        return []
    sinais: list[SinalConta] = []

    def gravar(codigo: str, **valores) -> None:
        sinais.append(_gravar(db, tenant_id, conta_id, codigo, confianca=1.0, fonte="cadastro_publico_cnpj", agora=agora, **valores))

    idade = _anos_desde(registro.get("data_inicio_atividade"), agora.date())
    if idade is not None and idade >= 0:
        gravar("IDADE_ANOS", num=idade, texto=str(registro.get("data_inicio_atividade"))[:10])
    capital = registro.get("capital_social")
    if isinstance(capital, (int, float)) and not isinstance(capital, bool):
        gravar("CAPITAL_SOCIAL", num=float(capital))
    if isinstance(registro.get("qsa"), list):
        gravar("QTD_SOCIOS", num=len(registro["qsa"]))
    if isinstance(registro.get("opcao_pelo_simples"), bool):
        gravar("OPTANTE_SIMPLES", num=1 if registro["opcao_pelo_simples"] else 0)
    situacao = (registro.get("descricao_situacao_cadastral") or "").strip()
    if situacao:
        gravar("SITUACAO_CADASTRAL", texto=situacao.upper())
    return sinais


# --- Leitura --------------------------------------------------------------------------------------------------------------

def vigentes(db: Session, tenant_id: str, conta_ids: list[int], codigos: list[str] | None = None) -> dict[int, dict[str, SinalConta]]:
    if not conta_ids:
        return {}
    consulta = db.query(SinalConta).filter(SinalConta.tenant_id == tenant_id, SinalConta.conta_id.in_(conta_ids), SinalConta.vigente.is_(True))
    if codigos is not None:
        consulta = consulta.filter(SinalConta.codigo.in_(codigos))
    por_conta: dict[int, dict[str, SinalConta]] = {}
    for sinal in consulta.order_by(SinalConta.observado_em, SinalConta.id):
        por_conta.setdefault(sinal.conta_id, {})[sinal.codigo] = sinal
    return por_conta


def sinal_para_dict(sinal: SinalConta) -> dict:
    item = CATALOGO.get(sinal.codigo, {})
    return {
        "codigo": sinal.codigo, "rotulo": item.get("rotulo", sinal.codigo), "tipo": item.get("tipo"), "valor_num": sinal.valor_num,
        "valor_texto": sinal.valor_texto, "confianca": sinal.confianca, "fonte": sinal.fonte, "url_evidencia": sinal.url_evidencia,
        "trecho": sinal.trecho, "observado_em": sinal.observado_em,
    }


def catalogo() -> list[dict]:
    return [{"codigo": codigo, **item} for codigo, item in CATALOGO.items()]


# --- Critérios e coorte ---------------------------------------------------------------------------------------------------

def validar_criterios(criterios: list[dict] | None) -> list[dict]:
    """Normaliza os critérios do ICP; recusa código fora do catálogo e regra que não cabe no tipo do sinal."""
    normalizados: list[dict] = []
    for criterio in criterios or []:
        codigo, regra = criterio.get("codigo"), criterio.get("regra")
        if codigo not in CATALOGO:
            raise ValidacaoFalhou(f"Sinal desconhecido: {codigo}.")
        if regra not in REGRAS:
            raise ValidacaoFalhou(f"Regra inválida para {codigo}: use exigir, excluir ou faixa.")
        tipo = CATALOGO[codigo]["tipo"]
        item = {"codigo": codigo, "regra": regra}
        if regra == "faixa":
            if tipo != "num":
                raise ValidacaoFalhou(f"{CATALOGO[codigo]['rotulo']}: faixa só vale para sinal numérico.")
            minimo, maximo = criterio.get("minimo"), criterio.get("maximo")
            if minimo is None and maximo is None:
                raise ValidacaoFalhou(f"{CATALOGO[codigo]['rotulo']}: informe mínimo, máximo ou os dois.")
            if minimo is not None and maximo is not None and minimo > maximo:
                raise ValidacaoFalhou(f"{CATALOGO[codigo]['rotulo']}: mínimo maior que o máximo.")
            item.update(minimo=minimo, maximo=maximo)
        elif tipo == "texto":
            valor = (criterio.get("valor") or "").strip()
            if not valor:
                raise ValidacaoFalhou(f"{CATALOGO[codigo]['rotulo']}: informe o valor a {regra}.")
            item["valor"] = valor.upper()
        elif tipo == "num":
            raise ValidacaoFalhou(f"{CATALOGO[codigo]['rotulo']}: sinal numérico usa a regra faixa.")
        normalizados.append(item)
    return normalizados


def _bate(criterio: dict, sinal: SinalConta | None) -> bool:
    """O sinal mostra o que o critério descreve? Sem sinal (dado não coletado) nunca bate."""
    if sinal is None:
        return False
    tipo = CATALOGO[criterio["codigo"]]["tipo"]
    if criterio["regra"] == "faixa":
        if sinal.valor_num is None:
            return False
        return (criterio.get("minimo") is None or sinal.valor_num >= criterio["minimo"]) and (
            criterio.get("maximo") is None or sinal.valor_num <= criterio["maximo"])
    if tipo == "texto":
        return (sinal.valor_texto or "").upper() == criterio["valor"]
    return sinal.valor_num == 1


def _descrever(criterio: dict, sinal: SinalConta | None) -> str:
    rotulo = CATALOGO[criterio["codigo"]]["rotulo"]
    if sinal is None:
        return f"{rotulo}: não coletado"
    valor = sinal.valor_texto if CATALOGO[criterio["codigo"]]["tipo"] == "texto" else (
        ("sim" if sinal.valor_num == 1 else "não") if CATALOGO[criterio["codigo"]]["tipo"] == "bool" else f"{sinal.valor_num:g}")
    return f"{rotulo}: {valor}"


@dataclass
class Avaliacao:
    atende: bool
    motivos: list[str]  # o que fez a conta entrar (ou, se não entrou, o que faltou)


def avaliar(criterios: list[dict], sinais_da_conta: dict[str, SinalConta]) -> Avaliacao:
    motivos_ok: list[str] = []
    faltas: list[str] = []
    for criterio in criterios:
        sinal = sinais_da_conta.get(criterio["codigo"])
        descricao = _descrever(criterio, sinal)
        if criterio["regra"] == "excluir":
            # Excluir só tira quem MOSTRA o sinal: dado não coletado não exclui ninguém.
            if _bate(criterio, sinal):
                faltas.append(f"Excluída por {descricao}")
            else:
                motivos_ok.append(f"Sem {CATALOGO[criterio['codigo']]['rotulo'].lower()}" if sinal is not None else descricao)
        elif _bate(criterio, sinal):
            motivos_ok.append(descricao)
        else:
            faltas.append(descricao)
    return Avaliacao(atende=not faltas, motivos=motivos_ok if not faltas else faltas)


def coorte(db: Session, tenant_id: str, criterios: list[dict], consulta: Query, icp_id: int | None = None, limite: int = 50) -> dict:
    """Contas de `consulta` (o escopo do usuário, montado por quem chama) que atendem a TODOS os critérios, com o motivo de cada uma.
    Conta descartada fica fora; `icp_id` limita às contas daquele ICP."""
    criterios = validar_criterios(criterios)
    consulta = consulta.filter(Conta.tenant_id == tenant_id, Conta.status != "descartada")
    if icp_id is not None:
        consulta = consulta.filter(Conta.icp_id == icp_id)
    contas = consulta.with_entities(Conta.id, Conta.nome).order_by(Conta.id).all()
    sinais_por_conta = vigentes(db, tenant_id, [c.id for c in contas], [c["codigo"] for c in criterios]) if criterios else {}
    atendem: list[dict] = []
    for conta_id, nome in contas:
        avaliacao = avaliar(criterios, sinais_por_conta.get(conta_id, {}))
        if avaliacao.atende:
            atendem.append({"conta_id": conta_id, "nome": nome, "motivos": avaliacao.motivos})
    return {"total": len(atendem), "avaliadas": len(contas), "contas": atendem[:limite]}


# --- Prompt da cadência ---------------------------------------------------------------------------------------------------

def _frase(sinal: SinalConta) -> str | None:
    if sinal.codigo == "PAGINA_VAGAS" and sinal.valor_num == 1:
        return "publica vagas abertas no próprio site"
    if sinal.codigo == "PAGINA_RI" and sinal.valor_num == 1:
        return "mantém área de Relações com Investidores no site"
    if sinal.codigo == "PUBLICA_PRIVACIDADE_LGPD" and sinal.valor_num == 1:
        return "publica política de privacidade/LGPD no site"
    if sinal.codigo == "RECEITA_LIQUIDA_PUBLICADA" and sinal.valor_num:
        periodo = f" ({sinal.valor_texto})" if sinal.valor_texto else ""
        return f"publicou receita líquida de R$ {sinal.valor_num / 1e6:,.1f} milhões{periodo}".replace(",", "X").replace(".", ",").replace("X", ".")
    if sinal.codigo == "ANUNCIA_GOOGLE_ADS" and sinal.valor_num == 1:
        return "investe em anúncios no Google (tag de conversão no site)"
    if sinal.codigo == "ANUNCIA_META_ADS" and sinal.valor_num == 1:
        return "investe em anúncios na Meta (pixel no site)"
    if sinal.codigo == "VAGAS_EM_PLATAFORMA" and sinal.valor_num == 1:
        plataforma = f" ({sinal.valor_texto})" if sinal.valor_texto and sinal.valor_texto != "outra" else ""
        return f"está com processo seletivo aberto em plataforma de recrutamento{plataforma}"
    if sinal.codigo == "IDADE_ANOS" and sinal.valor_num is not None and sinal.valor_num >= 1:
        return f"tem {int(sinal.valor_num)} anos desde a abertura do CNPJ"
    return None


def fatos_para_prompt(db: Session, tenant_id: str, conta_id: int, confianca_minima: float = 0.6) -> list[str]:
    """Fatos verificados que podem ser ditos ao decisor (só sinais `na_mensagem`, positivos e com confiança suficiente)."""
    codigos = [c for c, item in CATALOGO.items() if item["na_mensagem"]]
    sinais_da_conta = vigentes(db, tenant_id, [conta_id], codigos).get(conta_id, {})
    fatos: list[str] = []
    for codigo in codigos:
        sinal = sinais_da_conta.get(codigo)
        if sinal is not None and sinal.confianca >= confianca_minima and (frase := _frase(sinal)):
            fatos.append(frase)
    return fatos
