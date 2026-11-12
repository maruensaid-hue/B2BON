"""Corpus anonimizado para pesquisa: troca de identificadores, classificação da decisão humana e evidência disponível na época da mensagem."""

from datetime import datetime, timedelta

from app.models.aprovacao import Aprovacao
from app.models.auditoria import AuditLog
from app.models.conta import Conta
from app.models.conteudo_pagina_site import ConteudoPaginaSite
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.sinal_conta import SinalConta
from app.services.corpus_pesquisa_service import Anonimizador, montar_corpus

T = "tenant-teste"
AGORA = datetime(2026, 11, 10, 12, 0, 0)


def _conta(db, **extra):
    dados = dict(tenant_id=T, nome="Indústria Zênite Parafusos Ltda", nome_fantasia="Zênite", dominio="zenite.com.br", cnpj="12.345.678/0001-90",
                 segmento="Indústria", porte="MEDIO", regiao="SP", status="prospectada") | extra
    conta = Conta(**dados)
    db.add(conta)
    db.flush()
    return conta


def _decisor(db, conta, **extra):
    dados = dict(tenant_id=T, conta_id=conta.id, nome="João Álvares de Souza", cargo="Diretor Comercial", email="joao@zenite.com.br", telefone="(11) 98888-7777") | extra
    decisor = Decisor(**dados)
    db.add(decisor)
    db.flush()
    return decisor


def _mensagem(db, decisor, conteudo, *, criada_em=AGORA, status="enviado", aprovacao="aprovado", **extra):
    mensagem = Mensagem(tenant_id=T, decisor_id=decisor.id, canal="email", conteudo=conteudo, status=status, criado_em=criada_em, **extra)
    db.add(mensagem)
    db.flush()
    ap = Aprovacao(tenant_id=T, mensagem_id=mensagem.id, status=aprovacao)
    db.add(ap)
    db.flush()
    return mensagem, ap


def test_troca_nome_empresa_e_contatos_com_ou_sem_acento(db_session):
    conta = _conta(db_session)
    decisor = _decisor(db_session, conta)
    anonimizar = Anonimizador(conta, decisor)

    texto = (
        "Olá, Joao Alvares! Vi que a Industria Zenite Parafusos (CNPJ 12.345.678/0001-90) tem site em https://www.zenite.com.br/sobre. "
        "Me chame em joao@zenite.com.br ou (11) 98888-7777. Abraços, ZÊNITE."
    )
    resultado = anonimizar(texto)

    for vazado in ("Joao", "Alvares", "Zenite", "Zênite", "ZÊNITE", "12.345.678", "zenite.com.br", "98888", "joao@"):
        assert vazado not in resultado, (vazado, resultado)
    assert "[PESSOA]" in resultado and "[EMPRESA]" in resultado and "[EMAIL]" in resultado and "[TELEFONE]" in resultado and "[CNPJ]" in resultado


def test_nao_troca_palavras_comuns_do_nome_da_empresa(db_session):
    conta = _conta(db_session, nome="Comércio e Serviços Brasil Ltda", nome_fantasia=None, dominio=None, cnpj=None)

    resultado = Anonimizador(conta, None)("Prestamos serviços de comércio para empresas do Brasil.")

    assert resultado == "Prestamos serviços de comércio para empresas do Brasil."  # nada identifica a conta nas palavras soltas


def test_padroes_de_contato_fora_do_cadastro_tambem_sao_trocados(db_session):
    resultado = Anonimizador(None, None)("Fale com outra@empresa.com, (21) 91234-5678, 11.222.333/0001-44 ou www.outra.com.br/x")

    assert "outra@" not in resultado and "91234" not in resultado and "11.222.333" not in resultado and "outra.com" not in resultado


def test_classifica_a_decisao_do_vendedor_e_separa_limpeza_administrativa(db_session):
    conta = _conta(db_session)
    decisor = _decisor(db_session, conta)
    sem_edicao, _ = _mensagem(db_session, decisor, "a", aprovacao="aprovado")
    editada, _ = _mensagem(db_session, decisor, "b", aprovacao="aprovado")
    rejeitada, ap_rej = _mensagem(db_session, decisor, "c", status="cancelado", aprovacao="rejeitado")
    limpeza, _ = _mensagem(db_session, decisor, "d", status="cancelado", aprovacao="rejeitado")
    pendente, _ = _mensagem(db_session, decisor, "e", status="aguardando_aprovacao", aprovacao="pendente")
    db_session.add_all([
        AuditLog(tenant_id=T, evento_tipo="mensagem_editada", entidade_tipo="mensagem", entidade_id=editada.id,
                 detalhes={"conteudo_anterior": "texto antigo de João Álvares", "conteudo_novo": "b"}),
        AuditLog(tenant_id=T, evento_tipo="aprovacao_rejeitada", entidade_tipo="aprovacao", entidade_id=ap_rej.id, detalhes={"motivo": "fato inventado sobre Zênite"}),
    ])
    db_session.commit()

    linhas = {linha["conteudo"]: linha for linha in montar_corpus(db_session, T)}

    assert linhas["a"]["decisao"] == "aprovada_sem_edicao"
    assert linhas["b"]["decisao"] == "aprovada_apos_edicao" and linhas["b"]["texto_antes_da_edicao"] == "texto antigo de [PESSOA]"
    assert linhas["c"]["decisao"] == "rejeitada_pelo_vendedor" and linhas["c"]["motivo_da_rejeicao"] == "fato inventado sobre [EMPRESA]"
    assert linhas["d"]["decisao"] == "cancelada_sem_decisao_de_conteudo"
    assert linhas["e"]["decisao"] == "pendente"


def test_evidencia_marca_o_que_existia_quando_a_mensagem_foi_gerada(db_session):
    conta = _conta(db_session)
    decisor = _decisor(db_session, conta)
    _mensagem(db_session, decisor, "oi")
    db_session.add_all([
        SinalConta(tenant_id=T, conta_id=conta.id, codigo="tem_pagina_carreiras", valor_num=1, confianca=0.9, fonte="pesquisa_no_site",
                   trecho="Trabalhe na Zênite", observado_em=AGORA - timedelta(days=3), vigente=False),
        SinalConta(tenant_id=T, conta_id=conta.id, codigo="tem_pixel", valor_num=1, confianca=0.8, fonte="indicadores_site", observado_em=AGORA + timedelta(days=2)),
        ConteudoPaginaSite(tenant_id=T, conta_id=conta.id, url="https://zenite.com.br", conteudo="x", coletado_em=AGORA + timedelta(days=1)),
    ])
    db_session.commit()

    [linha] = montar_corpus(db_session, T)

    antes, depois = linha["evidencias"]
    assert antes["existia_na_geracao"] is True and antes["vigente_hoje"] is False and antes["trecho"] == "Trabalhe na [EMPRESA]"
    assert depois["existia_na_geracao"] is False
    assert linha["paginas_do_site"] == {"quantidade": 1, "ultima_coleta": "2026-11-11", "pode_ter_mudado_depois_da_mensagem": True}


def test_exportar_nao_grava_nada_e_nao_traz_dado_de_outro_tenant(db_session):
    conta = _conta(db_session)
    decisor = _decisor(db_session, conta)
    _mensagem(db_session, decisor, "minha")
    outra = Conta(tenant_id="tenant-outro", nome="Outra SA", status="prospectada")
    db_session.add(outra)
    db_session.flush()
    outro_decisor = Decisor(tenant_id="tenant-outro", conta_id=outra.id, nome="Fulano Beltrano")
    db_session.add(outro_decisor)
    db_session.flush()
    db_session.add(Mensagem(tenant_id="tenant-outro", decisor_id=outro_decisor.id, canal="email", conteudo="alheia", status="enviado"))
    db_session.commit()
    antes = db_session.query(AuditLog).count()

    linhas = list(montar_corpus(db_session, T))

    assert [linha["conteudo"] for linha in linhas] == ["minha"]
    assert db_session.query(AuditLog).count() == antes and not db_session.dirty and not db_session.new
    assert linhas[0]["mensagem_ref"] == "msg_0001" and linhas[0]["conta_ref"] == "conta_0001"
