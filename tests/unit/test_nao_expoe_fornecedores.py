"""A plataforma não expõe fornecedores: nenhum nome de fornecedor em arquivo de tela (frontend) e, no servidor, só onde ele é tecnicamente inevitável
(URL do endpoint no adaptador e os caminhos de webhook que o próprio fornecedor chama)."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
NOMES = re.compile(r"lusha|anthropic|sendgrid|mercado\s?pago|brasil\s?api|brasilapi|openai", re.IGNORECASE)
# Servidor: onde o nome é inevitável. Tudo o mais deve usar o nome genérico.
PERMITIDOS_NO_SERVIDOR = {
    "app/providers/contact_enrichment/contatos_b2b.py",  # URL do endpoint do provedor
}


def _arquivos(base: str, extensoes: tuple[str, ...]):
    for caminho in (RAIZ / base).rglob("*"):
        if caminho.suffix in extensoes and "node_modules" not in caminho.parts and "__pycache__" not in caminho.parts:
            yield caminho


def test_frontend_nao_cita_nenhum_fornecedor():
    achados = []
    for caminho in _arquivos("frontend/src", (".ts", ".tsx")):
        if caminho.name == "fornecedores.ts":  # o próprio mascarador precisa reconhecer os nomes
            continue
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if NOMES.search(linha):
                achados.append(f"{caminho.relative_to(RAIZ)}:{numero}: {linha.strip()[:100]}")
    assert not achados, "Fornecedor citado na tela:\n" + "\n".join(achados)


def test_servidor_nao_cita_o_fornecedor_de_contatos_fora_do_adaptador():
    achados = []
    for caminho in _arquivos("app", (".py",)):
        relativo = caminho.relative_to(RAIZ).as_posix()
        if relativo in PERMITIDOS_NO_SERVIDOR:
            continue
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if re.search("lusha", linha, re.IGNORECASE):
                achados.append(f"{relativo}:{numero}")
    assert not achados, "Fornecedor de contatos citado no servidor:\n" + "\n".join(achados)


def test_mensagens_de_erro_do_servidor_nao_citam_fornecedores_de_ia_e_de_e_mail():
    achados = []
    padrao = re.compile(r"(raise \w+\(|motivo_falha=|mensagem=|detail=).*(anthropic|sendgrid|mercado\s?pago|brasilapi)", re.IGNORECASE)
    for caminho in _arquivos("app", (".py",)):
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                achados.append(f"{caminho.relative_to(RAIZ)}:{numero}: {linha.strip()[:100]}")
    assert not achados, "Fornecedor em mensagem ao usuário:\n" + "\n".join(achados)
