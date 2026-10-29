"""RLS no PostgreSQL de verdade, SEGUNDA etapa (D-111, auditoria A01): as tabelas que a primeira etapa deixou pendentes, os contextos privilegiados e os fluxos entre empresas.

Mesmo método da primeira etapa (`test_rls_postgres.py`): banco descartável, `alembic upgrade head` (a migração `a3c5e7b9d1f2` entra junto) e asserções com o papel de execução, sem
superusuário e sem BYPASSRLS. Exige `B2BON_TESTE_PG_URL`.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import rls
from app.models.comentario_post import ComentarioPost
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.conta import Conta
from app.models.licenca import Licenca
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.plano import Plano
from app.models.post_rede_social import PostRedeSocial
from app.models.reacao_post import ReacaoPost
from app.models.registro_oportunidade import RegistroOportunidade
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.models.sala_corporativa import SalaCorporativa
from app.models.canal_sala import CanalSala
from app.models.mensagem_sala import MensagemSala
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from tests.integration.test_rls_postgres import _com_tenant, _sessao, bancos  # noqa: F401 — `bancos` é a fixture (banco descartável + papel de execução)

pytestmark = pytest.mark.skipif(not os.environ.get("B2BON_TESTE_PG_URL"), reason="exige PostgreSQL (B2BON_TESTE_PG_URL)")


@pytest.fixture(scope="module")
def dados(bancos):  # noqa: F811
    """Linhas das tabelas da segunda etapa, carregadas com o dono (que não passa pelo RLS)."""
    ids: dict = {}
    with Session(bancos["dono"]) as s:
        s.add(Tenant(id="t-cons", razao_social="Cons", tenant_pai_id="t-pai", modo_cobranca="consolidada"))
        plano = Plano(nome="plano-de-prova", franquia_contas_mes=1, preco_mensal=0)
        s.add(plano)
        s.flush()
        for tenant in ("t-a", "t-b", "t-pai", "t-cons"):
            s.add(Licenca(tenant_id=tenant, plano_id=plano.id, status="ativa"))
        ids["u_a"] = Usuario(tenant_id="t-a", nome="Ana", email="a@x.com", papel="admin")
        ids["u_b"] = Usuario(tenant_id="t-b", nome="Beto", email="b@x.com", papel="admin")
        ids["u_c"] = Usuario(tenant_id="t-b", nome="Caio sem post", email="c@x.com", papel="user")
        s.add_all([ids["u_a"], ids["u_b"], ids["u_c"]])
        s.flush()
        for tenant, nome in (("t-a", "conta-a"), ("t-b", "conta-b"), ("t-pai", "conta-pai"), ("t-filho", "conta-filho")):
            s.add(Conta(tenant_id=tenant, nome=nome, status="prospect"))

        # Shoal: dois posts, um repost do post de A feito por B, e o que pendura no repost
        post_a = PostRedeSocial(tenant_id="t-a", usuario_autor_id=ids["u_a"].id, texto="post da A")
        post_b = PostRedeSocial(tenant_id="t-b", usuario_autor_id=ids["u_b"].id, texto="post da B")
        s.add_all([post_a, post_b])
        s.flush()
        repost = PostRedeSocial(tenant_id="t-b", usuario_autor_id=ids["u_b"].id, texto="repost", post_original_id=post_a.id)
        s.add(repost)
        s.flush()
        s.add(ComentarioPost(post_id=repost.id, tenant_id="t-b", usuario_id=ids["u_b"].id, texto="comentário no repost"))
        s.add(ReacaoPost(post_id=repost.id, tenant_id="t-b", usuario_id=ids["u_b"].id))
        ids.update(post_a=post_a.id, post_b=post_b.id, repost=repost.id)

        # Diretório: perfil visível de B com oferta; perfil oculto do pai com oferta
        s.add(PerfilEmpresa(tenant_id="t-b", nome_exibicao="B", visivel_no_diretorio=True))
        s.add(PerfilEmpresa(tenant_id="t-pai", nome_exibicao="Pai", visivel_no_diretorio=False))
        s.add(Oferta(tenant_id="t-b", nome="Oferta da B", descricao="vitrine da B"))
        s.add(Oferta(tenant_id="t-pai", nome="Oferta do pai", descricao="não aparece no diretório"))

        # Conexão aceita entre B e o pai (a seed da primeira etapa deixa pendente)
        s.query(ConexaoEmpresa).filter_by(tenant_id_origem="t-b", tenant_id_destino="t-pai").update({"status": "aceita"})

        # Relacionamentos comerciais: pública, privada e "só conexões"
        s.add(RelacionamentoEmpresarial(tenant_id_origem="t-a", tenant_id_destino="t-b", tipo="PARTNER_OF", visibilidade="publica"))
        s.add(RelacionamentoEmpresarial(tenant_id_origem="t-a", tenant_id_destino="t-b", tipo="SUPPLIER_OF", visibilidade="privada"))
        s.add(RelacionamentoEmpresarial(tenant_id_origem="t-b", tenant_id_destino="t-a", tipo="CUSTOMER_OF", visibilidade="conexoes"))

        # Sala entre A e B com um canal e uma mensagem
        sala_ab = s.query(SalaCorporativa).filter_by(tenant_id_a="t-a", tenant_id_b="t-b").one()
        canal = CanalSala(sala_id=sala_ab.id, tipo="GENERAL")
        s.add(canal)
        s.flush()
        s.add(MensagemSala(canal_id=canal.id, tenant_id_remetente="t-a", texto="oi, B"))
        ids["canal"] = canal.id

        # Registro de Oportunidade: duas na rede do pai, uma em outra rede
        for tenant, raiz, cnpj in (("t-filho", "t-pai", "11111111000191"), ("t-pai", "t-pai", "22222222000191"), ("t-b", "t-b", "33333333000191")):
            s.add(RegistroOportunidade(tenant_id=tenant, rede_raiz_tenant_id=raiz, vendedor_usuario_id=ids["u_b"].id, cnpj=cnpj, nome_empresa=f"Empresa {cnpj}",
                                       status="ativo", expira_em=__import__("datetime").datetime(2099, 1, 1)))
        s.commit()
        ids["u_a"], ids["u_b"], ids["u_c"] = ids["u_a"].id, ids["u_b"].id, ids["u_c"].id
    return ids


def _coluna(sessao: Session, sql: str) -> set:
    return {linha[0] for linha in sessao.execute(text(sql)).all()}


def test_usuario_so_o_do_proprio_tenant_e_so_as_buscas_abrem_o_resto(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:
        assert _coluna(s, "SELECT email FROM usuario") == {"a@x.com"}
    with _sessao(bancos) as s:
        assert _coluna(s, "SELECT email FROM usuario") == set()  # sem contexto, nada
        with rls.contexto_busca(s, rls.ESCOPO_LOGIN, "b@x.com"):
            assert _coluna(s, "SELECT email FROM usuario") == {"b@x.com"}  # entrar: a linha cujo e-mail coincide
        with rls.contexto_busca(s, rls.ESCOPO_AUTENTICACAO, str(dados["u_a"])):
            assert _coluna(s, "SELECT email FROM usuario") == {"a@x.com"}  # validar o token: a linha do id


def test_conta_hierarquia_amplia_so_a_leitura_e_a_escrita_vai_no_tenant_certo(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-pai") as s:
        assert _coluna(s, "SELECT nome FROM conta") == {"conta-pai"}
        rls.ampliar_leitura(s, ["t-filho"])
        assert _coluna(s, "SELECT nome FROM conta") == {"conta-pai", "conta-filho"}
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO conta (tenant_id, nome, status) VALUES ('t-filho', 'invasora', 'prospect')"))  # a leitura ampliada não deixa gravar
        s.rollback()
        with rls.contexto_tenant(s, "t-filho"):  # o que a aplicação faz depois de conferir a subárvore (`saude_conta`)
            s.execute(text("UPDATE conta SET nome = 'conta-filho' WHERE nome = 'conta-filho'"))
            s.commit()


@pytest.mark.parametrize("escopo", ["plataforma", "sistema:qualquer-rotina"])
def test_contextos_privilegiados_veem_e_gravam_em_todos_os_tenants(bancos, dados, escopo):  # noqa: F811
    with _sessao(bancos) as s:
        rls.definir(s, rls.ContextoRls(escopo=escopo))
        assert {"conta-a", "conta-b", "conta-pai", "conta-filho"} <= _coluna(s, "SELECT nome FROM conta")
        assert s.execute(text("UPDATE conta SET nome = nome WHERE nome = 'conta-b'")).rowcount == 1
        s.rollback()


@pytest.mark.parametrize("escopo", ["autenticacao", "login", "chave-api", "tenant-inexistente"])
def test_busca_antes_do_tenant_nunca_ganha_o_acesso_dos_privilegiados(bancos, dados, escopo):  # noqa: F811
    with _sessao(bancos) as s:
        rls.definir(s, rls.ContextoRls(escopo=escopo, chave="qualquer"))
        assert _coluna(s, "SELECT nome FROM conta") == set()


def test_licenca_que_vale_e_a_do_tenant_que_paga(bancos, dados):  # noqa: F811
    """Cobrança consolidada: o filho enxerga a licença do pai (é a que `verificar_licenca_ativa` confere); o pai e os de cobrança direta só a própria."""
    with _com_tenant(bancos, "t-cons") as s:
        assert _coluna(s, "SELECT tenant_id FROM licenca") == {"t-cons", "t-pai"}
        assert s.execute(text("SELECT b2bon_cobrador()")).scalar() == "t-pai"
    with _com_tenant(bancos, "t-a") as s:
        assert _coluna(s, "SELECT tenant_id FROM licenca") == {"t-a"}
    with _com_tenant(bancos, "t-pai") as s:
        assert _coluna(s, "SELECT tenant_id FROM licenca") == {"t-pai"}
    with _com_tenant(bancos, "t-cons") as s:  # ler a do pai não dá o direito de alterá-la
        assert s.execute(text("UPDATE licenca SET status = 'suspensa' WHERE tenant_id = 't-pai'")).rowcount == 0


def test_feed_le_de_todos_mas_so_o_dono_grava_e_o_autor_do_original_apaga_o_repost(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:
        assert {"t-a", "t-b"} <= _coluna(s, "SELECT tenant_id FROM post_rede_social")
        assert s.execute(text("UPDATE post_rede_social SET texto = 'x' WHERE tenant_id = 't-b'")).rowcount == 0
        assert s.execute(text("DELETE FROM post_rede_social WHERE id = :i"), {"i": dados["post_b"]}).rowcount == 0  # post alheio, e não é repost de nada seu
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO post_rede_social (tenant_id, usuario_autor_id, texto) VALUES ('t-b', :u, 'forjado')"), {"u": dados["u_b"]})
        s.rollback()
    with _com_tenant(bancos, "t-a") as s:  # o repost é de B, mas é repost de um post de A: A pode apagá-lo com o que pendura nele
        assert s.execute(text("DELETE FROM comentario_post WHERE post_id = :i"), {"i": dados["repost"]}).rowcount == 1
        assert s.execute(text("DELETE FROM reacao_post WHERE post_id = :i"), {"i": dados["repost"]}).rowcount == 1
        assert s.execute(text("DELETE FROM post_rede_social WHERE id = :i"), {"i": dados["repost"]}).rowcount == 1
        s.rollback()


def test_nome_do_autor_vem_por_funcao_e_so_de_quem_tem_post_ou_comentario(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:
        assert _coluna(s, "SELECT email FROM usuario") == {"a@x.com"}  # a tabela continua fechada
        assert s.execute(text("SELECT b2bon_nome_do_autor(:i)"), {"i": dados["u_b"]}).scalar() == "Beto"  # autor de post de OUTRA empresa
        assert s.execute(text("SELECT b2bon_nome_do_autor(:i)"), {"i": dados["u_c"]}).scalar() is None  # usuário sem post nem comentário: a função não revela


def test_notificacao_insere_para_outra_empresa_mas_so_o_dono_le(bancos, dados):  # noqa: F811
    inserir = "INSERT INTO notificacao_rede_social (tenant_id, tipo, referencia_tipo, referencia_id, mensagem) VALUES ('t-b', 'new_comment', 'post_rede_social', 1, 'A comentou')"
    with _com_tenant(bancos, "t-a") as s:
        s.execute(text(inserir))  # sem RETURNING, como o serviço faz
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text(inserir + " RETURNING id"))  # RETURNING exigiria ler a linha da outra empresa
        s.rollback()
    with _com_tenant(bancos, "t-a") as s:
        s.execute(text(inserir))
        assert s.execute(text("SELECT count(*) FROM notificacao_rede_social")).scalar() == 0  # quem notificou não lê a notificação do outro
        s.commit()
    with _com_tenant(bancos, "t-b") as s:
        assert s.execute(text("SELECT count(*) FROM notificacao_rede_social")).scalar() == 1
        s.execute(text("DELETE FROM notificacao_rede_social"))
        s.commit()


def test_relacionamento_comercial_segue_a_visibilidade_declarada(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:  # parte de todos
        assert _coluna(s, "SELECT tipo FROM relacionamento_empresarial") == {"PARTNER_OF", "SUPPLIER_OF", "CUSTOMER_OF"}
    with _com_tenant(bancos, "t-pai") as s:  # não é parte; é conectado a B
        assert _coluna(s, "SELECT tipo FROM relacionamento_empresarial") == {"PARTNER_OF", "CUSTOMER_OF"}  # pública e "só conexões" (B é origem); a privada não
    with _com_tenant(bancos, "t-cons") as s:  # sem conexão nenhuma: só a pública
        assert _coluna(s, "SELECT tipo FROM relacionamento_empresarial") == {"PARTNER_OF"}


def test_filhos_da_sala_so_para_as_duas_empresas_da_sala(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:
        assert _coluna(s, "SELECT texto FROM mensagem_sala") == {"oi, B"}
        s.execute(text("INSERT INTO mensagem_sala (canal_id, tenant_id_remetente, texto) VALUES (:c, 't-a', 'segunda')"), {"c": dados["canal"]})
        s.rollback()
    with _com_tenant(bancos, "t-b") as s:  # a outra parte
        assert "oi, B" in _coluna(s, "SELECT texto FROM mensagem_sala")
    with _com_tenant(bancos, "t-pai") as s:  # tem sala com B, mas não com A: não lê o canal da sala A-B nem escreve nele
        assert _coluna(s, "SELECT texto FROM mensagem_sala") == set()
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(text("INSERT INTO mensagem_sala (canal_id, tenant_id_remetente, texto) VALUES (:c, 't-pai', 'intruso')"), {"c": dados["canal"]})
        s.rollback()


def test_registro_de_oportunidade_vale_na_rede_mas_so_o_dono_grava(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-filho") as s:
        assert _coluna(s, "SELECT cnpj FROM registro_oportunidade") == {"11111111000191", "22222222000191"}  # a rede do pai inteira (conflito de PRIME), não a de B
        assert s.execute(text("UPDATE registro_oportunidade SET status = 'cancelado' WHERE tenant_id = 't-pai'")).rowcount == 0
        s.rollback()


def test_vitrine_do_diretorio_so_de_perfil_que_o_diretorio_mostraria(bancos, dados):  # noqa: F811
    with _com_tenant(bancos, "t-a") as s:
        assert _coluna(s, "SELECT nome FROM oferta") == set()  # a tabela de ofertas de outras empresas continua fechada
        assert s.execute(text("SELECT nome FROM b2bon_oferta_principal('t-b')")).scalar() == "Oferta da B"  # perfil visível
        assert s.execute(text("SELECT nome FROM b2bon_oferta_principal('t-pai')")).first() is None  # perfil oculto e sem conexão com A
    with _com_tenant(bancos, "t-b") as s:  # conectado ao pai
        assert s.execute(text("SELECT nome FROM b2bon_oferta_principal('t-pai')")).scalar() == "Oferta do pai"


def test_identidades_da_rede_qualquer_tenant_cria_e_ajusta_mas_so_privilegiado_apaga(bancos, dados):  # noqa: F811
    """Ao declarar um relacionamento a aplicação cria a identidade do OUTRO lado; o cadastro é público (CNPJ e nomes), então isso é permitido, com `RETURNING`."""
    with _com_tenant(bancos, "t-a") as s:
        s.execute(text(
            "INSERT INTO empresa_rede (tenant_id, cnpj, razao_social, nome_exibicao, status, origem) VALUES ('t-b', NULL, 'B', 'B', 'REIVINDICADA', 'TENANT') RETURNING id"
        ))
        assert s.execute(text("UPDATE empresa_rede SET nome_exibicao = 'B2' WHERE tenant_id = 't-b'")).rowcount == 1
        assert s.execute(text("DELETE FROM empresa_rede WHERE tenant_id = 't-b'")).rowcount == 0  # apagar identidade não é de tenant
        s.commit()
    with _sessao(bancos) as s:
        assert s.execute(text("SELECT count(*) FROM empresa_rede")).scalar() == 0  # sem contexto, nem o cadastro público abre
        rls.definir(s, rls.ContextoRls(escopo="plataforma"))
        assert s.execute(text("DELETE FROM empresa_rede WHERE tenant_id = 't-b'")).rowcount == 1
        s.commit()
