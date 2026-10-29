"""RLS no PostgreSQL de verdade (D-110, auditoria A01). Exige `B2BON_TESTE_PG_URL` apontando para um servidor onde o usuário possa criar banco e papel (no CI, o `postgres` do job).

Cada execução cria um banco descartável, aplica `alembic upgrade head` (a migração `e7a9c1d3f5b8` entra junto) e cria o papel de EXECUÇÃO com o mesmo SQL que a operação usa
(`rls_sql.sql_papel_aplicacao`). As asserções rodam com esse papel (sem superusuário, sem BYPASSRLS); a carga de dados roda com o dono. O pool da aplicação tem UMA conexão, então
todo teste de "reaproveitamento" reaproveita de fato a mesma conexão física.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import rls, rls_registro, rls_sql
from app.models.bloqueio_contato import BloqueioContato
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.convite_cadastro import ConviteCadastro
from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.regra_aprendida import RegraAprendida
from app.models.sala_corporativa import SalaCorporativa
from app.models.tenant import Tenant

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="exige PostgreSQL (B2BON_TESTE_PG_URL)")

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bancos():
    sufixo = secrets.token_hex(4)
    nome_banco, papel, senha = f"b2bon_rls_{sufixo}", f"b2bon_rls_app_{sufixo}", secrets.token_urlsafe(24)
    base = make_url(URL)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conexao:
        conexao.execute(text(f'CREATE DATABASE "{nome_banco}"'))
    url_dono = base.set(database=nome_banco)
    ambiente = {
        **os.environ,
        "DATABASE_URL": url_dono.render_as_string(hide_password=False),
        "CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    }
    ambiente.pop("MIGRATION_DATABASE_URL", None)
    resultado = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RAIZ, env=ambiente, capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr[-2000:]

    dono = create_engine(url_dono)
    with dono.begin() as conexao:
        for comando in rls_sql.sql_papel_aplicacao(papel, senha):
            conexao.execute(text(comando))
    # Uma única conexão física: o que vazaria entre requisições aparece aqui.
    app = create_engine(url_dono.set(username=papel, password=senha), pool_size=1, max_overflow=0)
    _semear(dono)
    yield {"dono": dono, "app": app, "papel": papel}
    app.dispose()
    dono.dispose()
    with admin.connect() as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome_banco}" WITH (FORCE)'))
        conexao.execute(text(f"DROP ROLE IF EXISTS {papel}"))
    admin.dispose()


def _semear(dono) -> None:
    with Session(dono) as s:
        s.add_all([Tenant(id="t-a", razao_social="A"), Tenant(id="t-b", razao_social="B"), Tenant(id="t-pai", razao_social="Pai", tipo="distribuidor")])
        s.flush()
        s.add(Tenant(id="t-filho", razao_social="Filho", tenant_pai_id="t-pai"))
        s.flush()
        for t in ("t-a", "t-b", "t-pai", "t-filho"):
            s.add(BloqueioContato(tenant_id=t, email=f"{t}@x.com", motivo="teste", origem="teste"))
        for t in ("t-a", "t-b"):
            s.add(RegraAprendida(tenant_id=t, regra=f"regra de {t}", ativa=True))
        s.add_all([ConexaoEmpresa(tenant_id_origem="t-a", tenant_id_destino="t-b"), ConexaoEmpresa(tenant_id_origem="t-b", tenant_id_destino="t-pai")])
        s.add_all([SalaCorporativa(tenant_id_a="t-a", tenant_id_b="t-b"), SalaCorporativa(tenant_id_a="t-b", tenant_id_b="t-pai")])
        s.add_all([
            MensagemRedeSocial(tenant_id_remetente="t-a", tenant_id_destinatario="t-b", texto="oi"),
            MensagemRedeSocial(tenant_id_remetente="t-b", tenant_id_destinatario="t-pai", texto="olá"),
        ])
        s.add_all([ConviteCadastro(tenant_id="t-a", codigo="COD-A", papel_concedido="user"), ConviteCadastro(tenant_id="t-b", codigo="COD-B", papel_concedido="user")])
        s.commit()


def _sessao(bancos, **opcoes) -> Session:
    return Session(bancos["app"], **opcoes)


def _com_tenant(bancos, tenant: str, **opcoes) -> Session:
    sessao = _sessao(bancos, **opcoes)
    rls.definir_tenant(sessao, tenant)
    return sessao


def _emails(sessao: Session) -> set[str]:
    return {e for (e,) in sessao.execute(text("SELECT email FROM bloqueio_contato")).all()}


def test_papel_de_execucao_nao_e_superusuario_nem_ignora_rls(bancos):
    with bancos["dono"].connect() as conexao:
        linha = conexao.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :p"), {"p": bancos["papel"]}).one()
    assert tuple(linha) == (False, False)


def test_sem_contexto_o_banco_nega_tudo_o_que_e_do_tenant(bancos):
    with _sessao(bancos) as s:
        assert _emails(s) == set()
        assert s.execute(text("SELECT count(*) FROM regra_aprendida")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM conexao_empresa")).scalar() == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO bloqueio_contato (tenant_id, motivo, origem, criado_em) VALUES ('t-a', 'x', 'x', now())"))


def test_tenant_ve_so_as_proprias_linhas(bancos):
    with _com_tenant(bancos, "t-a") as s:
        assert _emails(s) == {"t-a@x.com"}
    with _com_tenant(bancos, "t-b") as s:
        assert _emails(s) == {"t-b@x.com"}


def test_inserir_para_outro_tenant_e_recusado(bancos):
    with _com_tenant(bancos, "t-a") as s:
        s.add(BloqueioContato(tenant_id="t-b", email="invasor@x.com", motivo="x", origem="x"))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
        s.rollback()
    with _com_tenant(bancos, "t-a") as s:  # e inserir para si mesmo continua valendo
        s.add(BloqueioContato(tenant_id="t-a", email="meu@x.com", motivo="x", origem="x"))
        s.commit()
        s.execute(text("DELETE FROM bloqueio_contato WHERE email = 'meu@x.com'"))
        s.commit()


def test_atualizar_e_excluir_linha_de_outro_tenant_nao_afeta_nada(bancos):
    with _com_tenant(bancos, "t-a") as s:
        assert s.execute(text("UPDATE bloqueio_contato SET motivo = 'hack' WHERE tenant_id = 't-b'")).rowcount == 0
        assert s.execute(text("DELETE FROM bloqueio_contato WHERE tenant_id = 't-b'")).rowcount == 0
        s.commit()
    with bancos["dono"].connect() as conexao:
        assert conexao.execute(text("SELECT motivo FROM bloqueio_contato WHERE tenant_id = 't-b'")).scalar() == "teste"


def test_mover_a_propria_linha_para_outro_tenant_e_recusado(bancos):
    with _com_tenant(bancos, "t-a") as s:
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("UPDATE bloqueio_contato SET tenant_id = 't-b' WHERE tenant_id = 't-a'"))
        s.rollback()


def test_hierarquia_amplia_so_a_leitura(bancos):
    with _com_tenant(bancos, "t-pai") as s:
        assert _emails(s) == {"t-pai@x.com"}  # sem ampliação, nem o filho aparece
        rls.ampliar_leitura(s, ["t-pai", "t-filho"])
        assert _emails(s) == {"t-pai@x.com", "t-filho@x.com"}
        assert s.execute(text("UPDATE bloqueio_contato SET motivo = 'x' WHERE tenant_id = 't-filho'")).rowcount == 0  # ler não é gravar
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO bloqueio_contato (tenant_id, motivo, origem, criado_em) VALUES ('t-filho', 'x', 'x', now())"))
        s.rollback()
    with _com_tenant(bancos, "t-filho") as s:  # o filho nunca enxerga o pai
        rls.ampliar_leitura(s, ["t-filho"])
        assert _emails(s) == {"t-filho@x.com"}


def test_super_admin_le_todos_mas_nao_grava_fora_do_proprio_tenant(bancos):
    with _com_tenant(bancos, "t-a") as s:
        rls.ampliar_leitura(s, rls.LEITURA_TOTAL)
        assert _emails(s) == {"t-a@x.com", "t-b@x.com", "t-pai@x.com", "t-filho@x.com"}
        assert s.execute(text("DELETE FROM bloqueio_contato WHERE tenant_id = 't-b'")).rowcount == 0
        s.rollback()


def test_tabela_de_duas_partes_so_aparece_para_as_partes(bancos):
    consulta = text("SELECT tenant_id_origem || '>' || tenant_id_destino FROM conexao_empresa")
    with _com_tenant(bancos, "t-a") as s:
        assert {r for (r,) in s.execute(consulta)} == {"t-a>t-b"}
    with _com_tenant(bancos, "t-b") as s:
        assert {r for (r,) in s.execute(consulta)} == {"t-a>t-b", "t-b>t-pai"}
    with _com_tenant(bancos, "t-filho") as s:
        assert s.execute(consulta).all() == []
    with _com_tenant(bancos, "t-a") as s:
        s.add(ConexaoEmpresa(tenant_id_origem="t-b", tenant_id_destino="t-pai"))  # a empresa A não é parte
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
        s.rollback()
    with _com_tenant(bancos, "t-a") as s:
        assert s.execute(text("SELECT count(*) FROM sala_corporativa")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM mensagem_rede_social")).scalar() == 1


def test_busca_antes_do_tenant_libera_so_a_linha_da_chave_e_so_para_leitura(bancos):
    with _sessao(bancos) as s:
        with rls.contexto_busca(s, rls.ESCOPO_CONVITE_CADASTRO, "COD-A"):
            assert {c for (c,) in s.execute(text("SELECT codigo FROM convite_cadastro"))} == {"COD-A"}
            assert s.execute(text("UPDATE convite_cadastro SET status = 'usado'")).rowcount == 0  # busca não altera
        with rls.contexto_busca(s, rls.ESCOPO_CONVITE_CADASTRO, "NAO-EXISTE"):
            assert s.execute(text("SELECT count(*) FROM convite_cadastro")).scalar() == 0
        with rls.contexto_busca(s, rls.ESCOPO_CAPTURA_LEAD, "COD-A"):  # o escopo de OUTRA busca não abre esta tabela
            assert s.execute(text("SELECT count(*) FROM convite_cadastro")).scalar() == 0
        assert rls.contexto_atual(s).vazio


def test_busca_e_depois_tenant_como_nos_fluxos_publicos(bancos):
    """Padrão dos webhooks e links: acha o tenant pela chave e continua como esse tenant (só ele)."""
    with _sessao(bancos) as s:
        with rls.contexto_busca(s, rls.ESCOPO_CONVITE_CADASTRO, "COD-B"):
            convite = s.execute(text("SELECT tenant_id FROM convite_cadastro")).one()
        rls.definir_tenant(s, convite.tenant_id)
        assert _emails(s) == {"t-b@x.com"}


def _criar_tabelas_de_prova(dono) -> None:
    """Tabelas descartáveis que exercitam os tipos de política que a primeira etapa ainda não aplica a tabelas reais (sistema, leitura compartilhada, escopo herdado)."""
    with dono.begin() as conexao:
        conexao.execute(text("DROP TABLE IF EXISTS prova_filha, prova_pai, prova_publica, prova_sistema"))
        conexao.execute(text("CREATE TABLE prova_pai (id integer PRIMARY KEY, tenant_id text NOT NULL)"))
        conexao.execute(text("CREATE TABLE prova_filha (id serial PRIMARY KEY, pai_id integer NOT NULL)"))
        conexao.execute(text("CREATE TABLE prova_publica (id serial PRIMARY KEY, tenant_id text NOT NULL, texto text)"))
        conexao.execute(text("CREATE TABLE prova_sistema (id serial PRIMARY KEY, tenant_id text NOT NULL, texto text)"))
        conexao.execute(text(
            "CREATE OR REPLACE FUNCTION b2bon_prova_pai_do_tenant(integer) RETURNS boolean LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public, pg_temp "
            "AS $$ SELECT EXISTS (SELECT 1 FROM prova_pai WHERE id = $1 AND tenant_id = b2bon_tenant()) $$"
        ))
        conexao.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON prova_pai, prova_filha, prova_publica, prova_sistema TO PUBLIC"))
        conexao.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO PUBLIC"))
        comandos = (
            rls_sql.sql_habilitar("prova_pai") + rls_sql.sql_tenant_direto("prova_pai")
            + rls_sql.sql_habilitar("prova_filha") + rls_sql.sql_herdada("prova_filha", "pai_id", "b2bon_prova_pai_do_tenant")
            + rls_sql.sql_habilitar("prova_publica") + rls_sql.sql_leitura_compartilhada("prova_publica")
            + rls_sql.sql_habilitar("prova_sistema") + rls_sql.sql_tenant_direto("prova_sistema")
            + rls_sql.sql_sistema("rotina-de-prova", "prova_sistema", "ler")
        )
        for comando in comandos:
            conexao.execute(text(comando))
        conexao.execute(text("INSERT INTO prova_pai (id, tenant_id) VALUES (1, 't-a'), (2, 't-b')"))
        conexao.execute(text("INSERT INTO prova_filha (pai_id) VALUES (1), (2)"))
        conexao.execute(text("INSERT INTO prova_publica (tenant_id, texto) VALUES ('t-a', 'da A'), ('t-b', 'da B')"))
        conexao.execute(text("INSERT INTO prova_sistema (tenant_id, texto) VALUES ('t-a', 'da A'), ('t-b', 'da B')"))


def test_escopo_herdado_segue_o_pai_e_o_with_check_vale_para_o_filho(bancos):
    _criar_tabelas_de_prova(bancos["dono"])
    with _com_tenant(bancos, "t-a") as s:
        assert {p for (p,) in s.execute(text("SELECT pai_id FROM prova_filha"))} == {1}
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO prova_filha (pai_id) VALUES (2)"))  # filho de um pai da empresa B
        s.rollback()
    with _sessao(bancos) as s:
        assert s.execute(text("SELECT count(*) FROM prova_filha")).scalar() == 0


def test_leitura_compartilhada_le_de_todos_mas_so_o_dono_grava(bancos):
    _criar_tabelas_de_prova(bancos["dono"])
    with _com_tenant(bancos, "t-a") as s:
        assert {t for (t,) in s.execute(text("SELECT texto FROM prova_publica"))} == {"da A", "da B"}
        assert s.execute(text("UPDATE prova_publica SET texto = 'x' WHERE tenant_id = 't-b'")).rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO prova_publica (tenant_id, texto) VALUES ('t-b', 'x')"))
        s.rollback()
    with _sessao(bancos) as s:  # sem contexto, nem a tabela compartilhada abre
        assert s.execute(text("SELECT count(*) FROM prova_publica")).scalar() == 0


def test_contexto_de_sistema_so_libera_a_tabela_e_o_modo_listados(bancos):
    _criar_tabelas_de_prova(bancos["dono"])
    with _sessao(bancos) as s:
        rls.definir(s, rls.ContextoRls(escopo="sistema:rotina-de-prova"))
        assert s.execute(text("SELECT count(*) FROM prova_sistema")).scalar() == 2  # ler, de todos os tenants
        assert s.execute(text("UPDATE prova_sistema SET texto = 'x'")).rowcount == 0  # "ler" não escreve
        assert s.execute(text("SELECT count(*) FROM bloqueio_contato")).scalar() == 0  # e não abre nenhuma outra tabela
        assert s.execute(text("SELECT count(*) FROM prova_pai")).scalar() == 0
        s.rollback()
    with _sessao(bancos) as s:
        rls.definir(s, rls.ContextoRls(escopo="sistema:outra-rotina"))
        assert s.execute(text("SELECT count(*) FROM prova_sistema")).scalar() == 0


def test_mesma_conexao_nao_vaza_contexto_entre_sessoes(bancos):
    pids = set()
    with _com_tenant(bancos, "t-a") as s:
        pids.add(s.execute(text("SELECT pg_backend_pid()")).scalar())
        assert _emails(s) == {"t-a@x.com"}
        s.commit()
    with _sessao(bancos) as s:  # próxima requisição, sem contexto, na MESMA conexão física
        pids.add(s.execute(text("SELECT pg_backend_pid()")).scalar())
        assert _emails(s) == set()
        assert s.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar() in (None, "")
    with _com_tenant(bancos, "t-b") as s:
        pids.add(s.execute(text("SELECT pg_backend_pid()")).scalar())
        assert _emails(s) == {"t-b@x.com"}
    assert len(pids) == 1  # provado: foi a mesma conexão


def test_contexto_sobrevive_a_commit_e_a_rollback_na_mesma_sessao(bancos):
    with _com_tenant(bancos, "t-a") as s:
        assert _emails(s) == {"t-a@x.com"}
        s.commit()
        assert _emails(s) == {"t-a@x.com"}  # transação nova: o contexto foi regravado
        s.rollback()
        assert _emails(s) == {"t-a@x.com"}


def test_erro_no_meio_da_transacao_nao_deixa_contexto_para_a_proxima(bancos):
    with _com_tenant(bancos, "t-a") as s:
        with pytest.raises(DBAPIError):
            s.execute(text("INSERT INTO bloqueio_contato (tenant_id, motivo, origem, criado_em) VALUES ('t-b', 'x', 'x', now())"))
        s.rollback()
    with _sessao(bancos) as s:
        assert _emails(s) == set()


def test_cron_por_tenant_enxerga_um_tenant_de_cada_vez(bancos):
    vistos = {}
    with _sessao(bancos) as s:
        for tenant in ("t-a", "t-b"):
            with rls.contexto_tenant(s, tenant):
                vistos[tenant] = _emails(s)
                s.commit()
        assert _emails(s) == set()  # fora da volta, sem contexto
    assert vistos == {"t-a": {"t-a@x.com"}, "t-b": {"t-b@x.com"}}


def test_o_que_estava_pendente_e_gravado_no_contexto_de_quem_criou(bancos):
    with _sessao(bancos, autoflush=False) as s:
        rls.definir_tenant(s, "t-a")
        s.add(BloqueioContato(tenant_id="t-a", email="pendente@x.com", motivo="x", origem="x"))
        rls.definir_tenant(s, "t-b")  # trocar de contexto grava antes o pendente, ainda como t-a
        s.commit()
    with _com_tenant(bancos, "t-a") as s:
        assert "pendente@x.com" in _emails(s)
        s.execute(text("DELETE FROM bloqueio_contato WHERE email = 'pendente@x.com'"))
        s.commit()


def test_o_registro_bate_com_o_que_o_banco_tem(bancos):
    with bancos["dono"].connect() as conexao:
        com_rls = {n for (n,) in conexao.execute(text("SELECT relname FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace AND relrowsecurity"))}
        com_politica = {n for (n,) in conexao.execute(text("SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public' AND policyname LIKE 'rls\\_%'"))}
    protegidas = set(rls_registro.TENANT_DIRETO) | set(rls_registro.DUAS_PARTES)
    provas = {"prova_pai", "prova_filha", "prova_publica", "prova_sistema"}
    assert protegidas <= com_rls and protegidas <= com_politica
    assert (com_rls - provas) == protegidas  # nenhuma tabela fora do registro ganhou RLS
    assert not (set(rls_registro.PENDENTES) | set(rls_registro.GLOBAIS)) & com_rls
