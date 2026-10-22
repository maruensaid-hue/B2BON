"""Remove o nome de fornecedores dos dados gravados que o usuário pode ver.

A plataforma não expõe nenhum fornecedor. O adaptador do provedor de contatos passou a se chamar `contatos` (e o cadastro público de CNPJ, `cadastro_publico`);
esta migração acerta o que já estava gravado:

* colunas de identificação (`provedor`, `fonte`, `origem`, `fornecedor`) cujo valor era exatamente o nome do fornecedor passam a `contatos` (ou `CONTATOS_B2B`
  no custo de infraestrutura), em todas as tabelas;
* a origem de campos enriquecidos e o uso por fonte do cadastro público, o texto "IA enriqueceu via ..." da linha do tempo e o prefixo do serviço de e-mail
  nos motivos de falha de envio;
* textos de motivo/aprovação/descrição das tabelas de enriquecimento e do custo de infraestrutura que citavam o fornecedor são reescritos de forma neutra;
* o link de fonte pública do preço do fornecedor é removido.

O trilho de auditoria (`audit_log`) e os registros de webhook não são reescritos: é histórico. Idempotente. Downgrade não restaura o nome (a remoção é intencional).

Revision ID: a1c3e5b7d9f1
Revises: f9b1d3e5a7c9
Create Date: 2026-10-22
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "a1c3e5b7d9f1"
down_revision = "f9b1d3e5a7c9"
branch_labels = None
depends_on = None

_NOME = "lusha"
_COLUNAS_DE_IDENTIFICACAO = ("provedor", "fonte", "origem", "fornecedor")
_COLUNAS_DE_TEXTO = ("motivo", "aprovado_por", "criado_por", "referencia", "descricao", "servico", "observacao", "nome")
_TABELAS_DE_TEXTO = ("custo_infraestrutura",)
_PREFIXOS_DE_TEXTO = ("enriquecimento_", "pesquisa_decisores")
_TROCAS = (
    ("po:custo-lusha-2026-10-21", "po:custo-contatos-2026-10-21"),
    ("APORTE-LUSHA-2026-10-21", "APORTE-CONTATOS-2026-10-21"),
    ("da Lusha", "do provedor de contatos"),
    ("na Lusha", "no provedor de contatos"),
    ("pela Lusha", "pelo provedor de contatos"),
    ("Lusha", "provedor de contatos"),
    ("LUSHA", "CONTATOS_B2B"),
    ("lusha", "contatos"),
)


_VALORES_DE_FONTE = {"brasilapi": "cadastro_publico", "brasilapi_cnpj": "cadastro_publico_cnpj"}
# (tabela, coluna, trecho antigo, trecho novo) — textos mostrados ao usuário
_TEXTOS_VISIVEIS = (
    ("atividade", "descricao", "IA enriqueceu via BrasilAPI", "IA enriqueceu com dados cadastrais públicos"),
    ("mensagem", "motivo_falha", "SendGrid ", "Falha do serviço de e-mail "),
    ("campanha_destinatario", "motivo_falha", "SendGrid ", "Falha do serviço de e-mail "),
    ("email_direto", "motivo_falha", "SendGrid ", "Falha do serviço de e-mail "),
)


def _neutro(texto: str) -> str:
    texto = re.sub(r"(?<!\w)a própria Lusha(?!\w)", "o próprio provedor", texto)
    texto = re.sub(r"(?<!\w)a Lusha(?!\w)", "o provedor de contatos", texto)
    for antigo, novo in _TROCAS:
        texto = texto.replace(antigo, novo)
    return texto


def upgrade() -> None:
    conexao = op.get_bind()
    inspetor = sa.inspect(conexao)
    for tabela in inspetor.get_table_names():
        colunas = {c["name"]: c for c in inspetor.get_columns(tabela)}
        referencia = sa.table(tabela, *[sa.column(nome) for nome in colunas])
        # 1) valores de identificação que eram exatamente o nome do fornecedor
        for nome in _COLUNAS_DE_IDENTIFICACAO:
            if nome in colunas:
                novo = "CONTATOS_B2B" if nome == "fornecedor" else "contatos"
                conexao.execute(sa.update(referencia).where(sa.func.lower(referencia.c[nome]) == _NOME).values({nome: novo}))
        # 1b) origem de campos enriquecidos e uso por fonte do cadastro público de CNPJ
        for nome in ("fonte", "origem"):
            if nome in colunas:
                for antigo, novo in _VALORES_DE_FONTE.items():
                    conexao.execute(sa.update(referencia).where(referencia.c[nome] == antigo).values({nome: novo}))
        # 1c) textos visíveis ao usuário
        for tabela_texto, coluna_texto, antigo, novo in _TEXTOS_VISIVEIS:
            if tabela == tabela_texto and coluna_texto in colunas and "id" in colunas:
                for id_, valor in conexao.execute(sa.select(referencia.c.id, referencia.c[coluna_texto]).where(referencia.c[coluna_texto].like(f"%{antigo}%"))).fetchall():
                    conexao.execute(sa.update(referencia).where(referencia.c.id == id_).values({coluna_texto: valor.replace(antigo, novo)}))
        # 2) textos que citam o fornecedor (só tabelas de enriquecimento e custo de infraestrutura)
        if tabela in _TABELAS_DE_TEXTO or tabela.startswith(_PREFIXOS_DE_TEXTO):
            if "id" not in colunas:
                continue
            for nome in _COLUNAS_DE_TEXTO:
                if nome not in colunas:
                    continue
                linhas = conexao.execute(sa.select(referencia.c.id, referencia.c[nome]).where(sa.func.lower(referencia.c[nome]).like(f"%{_NOME}%"))).fetchall()
                for id_, valor in linhas:
                    conexao.execute(sa.update(referencia).where(referencia.c.id == id_).values({nome: _neutro(valor)}))
        # 3) link da fonte pública do preço do fornecedor
        if "url_fonte" in colunas:
            conexao.execute(sa.update(referencia).where(sa.func.lower(referencia.c.url_fonte).like(f"%{_NOME}%")).values(url_fonte=None))


def downgrade() -> None:
    """Intencionalmente vazio: o nome do fornecedor não volta a ser gravado."""
