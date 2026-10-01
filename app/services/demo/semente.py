"""Dados fictícios do ambiente de demonstração (D-082) — empresa, equipe e operação inventadas, aplicações reais.

A empresa demonstrada (Atlas Soluções Industriais) vende manutenção preditiva, gestão de ativos e eficiência energética
para indústrias e para o setor público. Tudo aqui é fictício: nomes, e-mails (`*.demo.invalid`, domínio que nunca
entrega), telefones da faixa 90000-xxxx, CNPJs ausentes e links `https://*.demo.invalid`. Os fluxos com regra (licitações,
compras públicas e sourcing) passam pelas mesmas funções da API, então nascem em estados válidos.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.bids import contract as bids
from app.contexts.finops import contract as finops
from app.contexts.shared import demonstracao
from app.models.atividade import Atividade
from app.models.cadencia import Cadencia
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.interacao_conta import InteracaoConta
from app.models.lista_prospeccao import ListaProspeccao
from app.models.mensagem import Mensagem
from app.models.necessidade_oportunidade import NecessidadeOportunidade
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.pesquisa_nps import PesquisaNps
from app.models.proposta_negocio import PropostaNegocio
from app.models.reuniao import Reuniao
from app.models.toque_cadencia import ToqueCadencia
from app.models.usuario import Usuario
from app.services import crm_service

EMPRESA = "Atlas Soluções Industriais (demonstração)"
EQUIPE = (("Marina Costa", "admin", "Gestora comercial"), ("Rafael Lima", "user", "Executivo de contas"),
          ("Juliana Prado", "user", "Executiva de setor público"), ("Bruno Teixeira", "user", "SDR"))
# Um PDF mínimo válido — anexo das propostas de exemplo.
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")

OFERTAS = (
    ("Manutenção Preditiva IoT", "Sensores de vibração e temperatura com alertas de falha antes da parada.", 4800.0, "SaaS + hardware",
     ["Reduz paradas não planejadas", "Implantação em 30 dias"], ["Paradas não planejadas", "Custo de manutenção corretiva"]),
    ("Plataforma de Gestão de Ativos", "Inventário, planos de manutenção e ordens de serviço num só lugar.", 2900.0, "SaaS",
     ["Integra com ERP", "App para o técnico em campo"], ["Planilhas desatualizadas", "Falta de histórico dos ativos"]),
    ("Eficiência Energética", "Diagnóstico e monitoramento do consumo por linha de produção.", 6500.0, "Projeto + assinatura",
     ["Economia média de 12% na conta de energia"], ["Conta de energia alta", "Metas ESG"]),
    ("Licença Setor Público", "Gestão de ativos para prefeituras e autarquias, com contratação por licitação.", 9800.0, "Licença anual",
     ["Atende a Lei 14.133/2021", "Relatórios para o TCE"], ["Ativos públicos sem controle", "Auditoria do TCE"]),
)

# (nome, segmento, porte, região, status, aderência, cliente_desde em dias atrás ou None)
CONTAS = (
    ("Metalúrgica Horizonte S.A.", "Metalurgia", "GRANDE", "SP", "priorizada", 0.92, 420),
    ("Plásticos Vale Verde Ltda.", "Plásticos", "MEDIO", "SP", "priorizada", 0.88, 210),
    ("Cerâmica Pedra Alta Ltda.", "Cerâmica", "MEDIO", "SC", "priorizada", 0.81, None),
    ("Alimentos Serra Azul S.A.", "Alimentos", "GRANDE", "MG", "priorizada", 0.86, 95),
    ("Têxtil Rio Claro Ltda.", "Têxtil", "MEDIO", "SP", "prospectada", 0.74, None),
    ("Química Ipê Industrial Ltda.", "Química", "MEDIO", "PR", "priorizada", 0.79, None),
    ("Autopeças Cruzeiro Ltda.", "Automotivo", "MEDIO", "SP", "prospectada", 0.83, None),
    ("Embalagens Litoral S.A.", "Embalagens", "GRANDE", "RJ", "priorizada", 0.77, 300),
    ("Papel e Celulose Araucária S.A.", "Papel e celulose", "GRANDE", "PR", "prospectada", 0.9, None),
    ("Farmacêutica Nova Vida Ltda.", "Farmacêutico", "MEDIO", "GO", "prospectada", 0.69, None),
    ("Logística Bandeirantes Ltda.", "Logística", "MEDIO", "SP", "prospectada", 0.62, None),
    ("Agroindústria Cerrado Forte S.A.", "Agroindústria", "GRANDE", "MT", "priorizada", 0.85, None),
    ("Prefeitura Municipal de Vale do Sol", "Setor público", "GRANDE", "SP", "priorizada", 0.8, None),
    ("Companhia de Saneamento Rio Manso", "Setor público", "GRANDE", "MG", "priorizada", 0.84, None),
    ("Hospital Santa Clara", "Saúde", "MEDIO", "SP", "prospectada", 0.71, None),
)
LEADS_MANUAIS = (9, 10, 14)  # Farmacêutica, Logística e Hospital entraram por indicação/evento
CARGOS = (("Diretor(a) Industrial", "linkedin"), ("Gerente de Manutenção", "whatsapp"), ("Comprador(a) Sênior", "email"),
          ("Diretor(a) Financeiro(a)", "email"), ("Secretário(a) de Infraestrutura", "email"))
PESSOAS = ("Carlos Mendes", "Fernanda Rocha", "Paulo Siqueira", "Aline Barbosa", "Ricardo Nogueira", "Beatriz Campos", "Thiago Moura",
           "Larissa Fontes", "Eduardo Pires", "Camila Duarte", "Gustavo Ramos", "Patrícia Leal", "André Vasconcelos", "Renata Coelho",
           "Marcelo Antunes", "Sofia Albuquerque", "Diego Castro", "Natália Freitas", "Leonardo Brito", "Vanessa Lopes")

# (conta, oferta, estágio, valor, probabilidade, vendedor, dias desde a criação, perdido: motivo | None)
NEGOCIOS = (
    (0, 0, "Ganho", 14400.0, 100, 1, 160, None), (1, 1, "Ganho", 8700.0, 100, 1, 120, None),
    (3, 2, "Ganho", 19500.0, 100, 1, 80, None), (7, 1, "Ganho", 5800.0, 100, 3, 200, None),
    (2, 0, "Negociação", 9600.0, 70, 1, 35, None), (5, 2, "Negociação", 13000.0, 60, 1, 28, None),
    (8, 0, "Proposta", 24000.0, 45, 1, 21, None), (11, 1, "Proposta", 11600.0, 40, 3, 18, None),
    (12, 3, "Proposta", 117600.0, 50, 2, 40, None), (13, 3, "Descoberta", 98000.0, 25, 2, 9, None),
    (4, 1, "Descoberta", 5800.0, 20, 3, 6, None), (6, 0, "Descoberta", 9600.0, 20, 3, 4, None),
    (9, 2, "Perdido", 6500.0, 0, 1, 70, "Preço acima do orçamento aprovado"),
    (14, 1, "Perdido", 2900.0, 0, 3, 55, "Optou por manter o sistema atual"),
)


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _slug(nome: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in nome.lower().split(" (")[0])
    return "-".join(p for p in base.split("-") if p)[:30]


def _equipe(db: Session, tenant_id: str) -> list[Usuario]:
    usuarios = []
    for nome, papel, _ in EQUIPE:
        usuario = Usuario(tenant_id=tenant_id, nome=nome, email=f"{_slug(nome)}@{tenant_id}.demo.invalid", papel=papel, ativo=True,
                          termos_aceitos_em=_agora())
        db.add(usuario)
        usuarios.append(usuario)
    db.flush()
    return usuarios


def _icps_ofertas(db: Session, tenant_id: str) -> tuple[list[ICP], list[Oferta]]:
    icps = [ICP(tenant_id=tenant_id, grupo_id=f"{tenant_id}-industria", nome="Indústria de médio e grande porte — Sul/Sudeste",
                segmento="Indústria", porte="MEDIO", regiao="Sul e Sudeste",
                dores=["Paradas não planejadas", "Custo alto de manutenção corretiva", "Conta de energia elevada"],
                gatilhos=["Expansão de fábrica", "Troca de gestor de manutenção", "Meta ESG publicada"],
                cnae_codigos=["2539001", "2829199", "1091101"], ufs=["SP", "MG", "PR", "SC", "RJ"]),
            ICP(tenant_id=tenant_id, grupo_id=f"{tenant_id}-publico", nome="Municípios e autarquias acima de 100 mil habitantes",
                segmento="Setor público", porte="GRANDE", regiao="Sudeste",
                dores=["Ativos sem inventário", "Apontamentos do TCE"], gatilhos=["PCA publicado", "Edital de manutenção"],
                cnae_codigos=["8411600"], ufs=["SP", "MG"])]
    db.add_all(icps)
    db.flush()
    ofertas = []
    for i, (nome, descricao, ticket, modelo, diferenciais, dores) in enumerate(OFERTAS):
        oferta = Oferta(tenant_id=tenant_id, icp_id=icps[1 if i == 3 else 0].id, nome=nome, descricao=descricao, diferenciais=diferenciais,
                        provas_sociais=["Case Metalúrgica Horizonte: -38% de paradas em 6 meses"], faixa_preco_min=ticket * 0.8,
                        faixa_preco_max=ticket * 1.5, categoria="Serviço industrial" if i < 3 else "Setor público", dores=dores,
                        modelo_precificacao=modelo, ticket_medio=ticket, margem_media=0.42,
                        perguntas_descoberta=["Quantas paradas não planejadas no último trimestre?", "Quem aprova o orçamento de manutenção?"],
                        objecoes=["Já temos um sistema", "Orçamento só no ano que vem"])
        db.add(oferta)
        ofertas.append(oferta)
    db.flush()
    return icps, ofertas


def _contas(db: Session, tenant_id: str, icps, vendedores, lista) -> tuple[list[Conta], list[list[Decisor]]]:
    agora, contas, decisores = _agora(), [], []
    for i, (nome, segmento, porte, uf, status, aderencia, cliente_ha) in enumerate(CONTAS):
        publico = segmento == "Setor público"
        manual = i in LEADS_MANUAIS  # lead cadastrado à mão (tela Leads): sem ICP nem lista de prospecção
        conta = Conta(tenant_id=tenant_id, nome=nome, nome_fantasia=nome.split(" ")[0] + " " + nome.split(" ")[1], segmento=segmento,
                      porte=porte, regiao=uf, status=status, score_aderencia=None if manual else aderencia,
                      icp_id=None if manual else icps[1 if publico else 0].id,
                      lista_prospeccao_id=lista.id if cliente_ha is None and not manual else None,
                      vendedor_usuario_id=vendedores[i % len(vendedores)].id,
                      dominio=f"{_slug(nome)}.demo.invalid", origem="manual" if manual else "demonstracao",
                      cliente_desde=agora - timedelta(days=cliente_ha) if cliente_ha else None,
                      proximo_passo="Agendar visita técnica" if status == "priorizada" else "Primeiro contato pelo LinkedIn",
                      proximo_passo_em=agora + timedelta(days=(i % 5) + 1))
        db.add(conta)
        db.flush()
        pessoas = []
        for j in range(2 if i < 10 else 1):
            nome_pessoa = PESSOAS[(i * 2 + j) % len(PESSOAS)]
            cargo, canal = CARGOS[4 if publico else (i + j) % 4]
            pessoas.append(Decisor(tenant_id=tenant_id, conta_id=conta.id, nome=nome_pessoa, cargo=cargo, canal_provavel=canal,
                                   email=f"{_slug(nome_pessoa).replace('-', '.')}@{_slug(nome)}.demo.invalid",
                                   telefone=f"+55 11 90000-{1000 + i * 10 + j:04d}",
                                   linkedin_url=f"https://linkedin.demo.invalid/in/{_slug(nome_pessoa)}", origem="demonstracao"))
        db.add_all(pessoas)
        db.flush()
        contas.append(conta)
        decisores.append(pessoas)
    return contas, decisores


def _negocios(db: Session, tenant_id: str, contas, decisores, ofertas, usuarios) -> list[Negocio]:
    estagios = {e.nome: e for e in crm_service.garantir_estagios_padrao(db, tenant_id)}
    agora, negocios = _agora(), []
    for conta_i, oferta_i, estagio, valor, prob, vendedor_i, dias, motivo in NEGOCIOS:
        criado = agora - timedelta(days=dias)
        negocio = Negocio(tenant_id=tenant_id, conta_id=contas[conta_i].id, vendedor_usuario_id=usuarios[vendedor_i].id,
                          decisor_id=decisores[conta_i][0].id, estagio_id=estagios[estagio].id, oferta_id=ofertas[oferta_i].id,
                          nome=f"{ofertas[oferta_i].nome} — {contas[conta_i].nome_fantasia}", valor=valor, probabilidade=prob,
                          origem="manual", criado_em=criado, atualizado_em=agora - timedelta(days=min(dias, 3)),
                          ganho_em=criado + timedelta(days=dias // 2) if estagio == "Ganho" else None,
                          perdido_em=criado + timedelta(days=dias // 2) if motivo else None, motivo_perda=motivo)
        db.add(negocio)
        negocios.append(negocio)
    db.flush()
    for k, negocio in enumerate(n for n in negocios if n.estagio_id in (estagios["Proposta"].id, estagios["Negociação"].id)):
        db.add(PropostaNegocio(tenant_id=tenant_id, negocio_id=negocio.id, versao=1, nome="Proposta comercial", numero=k + 1,
                               nome_arquivo=f"proposta-{k + 1}.pdf", tipo_mime="application/pdf", conteudo=PDF, tamanho_bytes=len(PDF),
                               enviada_por_usuario_id=negocio.vendedor_usuario_id, criado_em=negocio.criado_em + timedelta(days=5)))
    return negocios


def _atividades(db: Session, tenant_id: str, contas, negocios) -> None:
    agora = _agora()
    roteiro = (("ligacao", "Ligação de descoberta: confirmou dor com paradas da linha 2", 12), ("email", "Envio do case Metalúrgica Horizonte", 9),
               ("reuniao", "Reunião técnica com manutenção e produção", 6), ("whatsapp", "Follow-up sobre visita técnica", 3),
               ("nota", "Decisor pediu proposta com implantação em duas fases", 1))
    for negocio in negocios:
        for tipo, descricao, dias in roteiro[: 3 if negocio.perdido_em else 5]:
            db.add(Atividade(tenant_id=tenant_id, conta_id=negocio.conta_id, negocio_id=negocio.id, usuario_id=negocio.vendedor_usuario_id,
                             tipo=tipo, descricao=descricao, criado_em=agora - timedelta(days=dias, hours=negocio.id % 7)))
    for conta in contas[4:]:  # prospecção: toques humanos em contas ainda sem negócio
        db.add(Atividade(tenant_id=tenant_id, conta_id=conta.id, usuario_id=conta.vendedor_usuario_id, tipo="linkedin",
                         descricao="Convite de conexão com mensagem personalizada", criado_em=agora - timedelta(days=2)))
        db.add(Atividade(tenant_id=tenant_id, conta_id=conta.id, usuario_id=None, tipo="sistema",
                         descricao="Conta adicionada à lista de prospecção", criado_em=agora - timedelta(days=4)))


def _reunioes(db: Session, tenant_id: str, contas, decisores, usuarios) -> None:
    agora = _agora()
    agenda = ((2, 1, 2, "agendada", None), (8, 1, 3, "agendada", None), (12, 2, 5, "agendada", None), (13, 2, 1, "agendada", None),
              (5, 1, -3, "realizada", True), (11, 3, -5, "realizada", True), (4, 3, -2, "realizada", False), (6, 3, -1, "no_show", None))
    for conta_i, vendedor_i, dias, status, qualificada in agenda:
        quando = (agora + timedelta(days=dias)).replace(hour=10 + conta_i % 6, minute=0, second=0, microsecond=0)
        db.add(Reuniao(tenant_id=tenant_id, conta_id=contas[conta_i].id, decisor_id=decisores[conta_i][0].id,
                       vendedor_id=str(usuarios[vendedor_i].id), data_hora=quando, status=status, horarios_propostos=[quando.isoformat()],
                       horario_confirmado=quando, link_reuniao=f"https://meet.demo.invalid/atlas-{conta_i}",
                       qualificada_confirmada=qualificada,
                       motivo_qualificacao="Orçamento aprovado para 2027 e dor confirmada" if qualificada else None,
                       resumo_ia=("Cliente relatou 6 paradas no trimestre; pediu proposta de manutenção preditiva para 40 motores."
                                  if status == "realizada" else None)))


def _prospeccao(db: Session, tenant_id: str, icps, ofertas, decisores, usuarios) -> None:
    agora = _agora()
    cadencias = [Cadencia(tenant_id=tenant_id, icp_id=icps[0].id, oferta_id=ofertas[0].id, nome="Indústrias SP — manutenção preditiva",
                          canais=["email", "linkedin", "whatsapp"], status="ativa", tipo="prospeccao", data_inicio=agora - timedelta(days=10),
                          cancelar_ao_responder=True),
                 Cadencia(tenant_id=tenant_id, icp_id=icps[1].id, oferta_id=ofertas[3].id, nome="Municípios — gestão de ativos públicos",
                          canais=["email"], status="aguardando_aprovacao", tipo="prospeccao", data_inicio=agora + timedelta(days=2)),
                 Cadencia(tenant_id=tenant_id, icp_id=icps[0].id, oferta_id=ofertas[2].id, nome="Nutrição — clientes de eficiência energética",
                          canais=["email"], status="ativa", tipo="nutricao", data_inicio=agora - timedelta(days=30))]
    db.add_all(cadencias)
    db.flush()
    toques = {}
    for cadencia in cadencias:
        for ordem, canal in enumerate(cadencia.canais * (2 if len(cadencia.canais) == 1 else 1), start=1):
            toque = ToqueCadencia(tenant_id=tenant_id, cadencia_id=cadencia.id, ordem=ordem, canal=canal, intervalo_dias_apos_anterior=0 if ordem == 1 else 3)
            db.add(toque)
            toques.setdefault(cadencia.id, []).append(toque)
    db.flush()
    textos = {"email": ("Paradas não planejadas na linha de produção?",
                        "Olá {nome}, vi que a {empresa} ampliou a fábrica. Empresas do seu setor reduziram 30% das paradas com manutenção "
                        "preditiva. Faz sentido uma conversa de 20 minutos na quinta?"),
              "linkedin": (None, "Olá {nome}! Acompanho a {empresa} e queria trocar uma ideia sobre confiabilidade de ativos."),
              "whatsapp": (None, "Oi {nome}, aqui é da Atlas. Posso te mandar o case de uma metalúrgica que cortou 38% das paradas?")}
    for k, pessoas in enumerate(decisores[4:12]):
        pessoa = pessoas[0]
        conta = db.get(Conta, pessoa.conta_id)
        for toque in toques[cadencias[0].id][: 1 + k % 3]:
            assunto, corpo = textos[toque.canal]
            pendente = toque.ordem == 1 + k % 3 and k % 2 == 0
            db.add(Mensagem(tenant_id=tenant_id, cadencia_id=cadencias[0].id, decisor_id=pessoa.id, toque_cadencia_id=toque.id,
                            canal=toque.canal, assunto=assunto, conteudo=corpo.format(nome=pessoa.nome.split()[0], empresa=conta.nome_fantasia),
                            status="aguardando_aprovacao" if pendente else "enviado",
                            agendado_para=agora + timedelta(hours=k) if pendente else None,
                            enviado_em=None if pendente else agora - timedelta(days=8 - toque.ordem * 2),
                            aberto_em=None if pendente or toque.canal != "email" else agora - timedelta(days=7 - toque.ordem * 2)))
    campanha = Campanha(tenant_id=tenant_id, nome="Convite — Webinar Indústria 4.0 na prática", tipo="marketing", canais=["email"],
                        assunto="Webinar: como reduzir 30% das paradas em 6 meses",
                        conteudo_email="Olá! Convidamos você para o nosso webinar com o case da Metalúrgica Horizonte.", status="rascunho")
    db.add(campanha)
    db.flush()
    for pessoas in decisores[:8]:
        db.add(CampanhaDestinatario(tenant_id=tenant_id, campanha_id=campanha.id, decisor_id=pessoas[0].id, nome=pessoas[0].nome,
                                    email=pessoas[0].email, status="pendente"))


def _relacionamento(db: Session, tenant_id: str, contas, decisores, negocios, usuarios) -> None:
    """MAP: saúde dos clientes, NPS e necessidades mapeadas nas oportunidades."""
    agora = _agora()
    sinais = {0: ("feedback_positivo", "Elogiou o painel de alertas na reunião mensal"), 1: ("ticket_suporte", "Dúvida sobre integração com o ERP"),
              3: ("reclamacao", "Sensor da linha 4 offline por dois dias"), 7: ("reuniao_remarcada", "Reunião de resultados remarcada pela segunda vez")}
    for conta_i, (tipo, descricao) in sinais.items():
        db.add(InteracaoConta(tenant_id=tenant_id, conta_id=contas[conta_i].id, tipo=tipo, descricao=descricao,
                              criado_por_usuario_id=usuarios[1].id, criado_em=agora - timedelta(days=conta_i + 2)))
        db.add(InteracaoConta(tenant_id=tenant_id, conta_id=contas[conta_i].id, tipo="contato", descricao="Check-in mensal",
                              criado_por_usuario_id=usuarios[1].id, criado_em=agora - timedelta(days=conta_i * 9 + 5)))
    for conta_i, nota in ((0, 10), (1, 8), (3, 5), (7, 9)):
        classificacao = "promotor" if nota >= 9 else "neutro" if nota >= 7 else "detrator"
        db.add(PesquisaNps(tenant_id=tenant_id, conta_id=contas[conta_i].id, decisor_id=decisores[conta_i][0].id, marco="entrega_concluida",
                           nota=nota, classificacao=classificacao, respondida_em=agora - timedelta(days=12)))
        contas[conta_i].nps_nota, contas[conta_i].nps_classificacao = nota, classificacao
    necessidades = (("dor", "Seis paradas não planejadas no trimestre na prensa principal", "confirmada"),
                    ("orcamento", "Orçamento de R$ 120 mil aprovado para 2027", "confirmada"),
                    ("prazo", "Quer o piloto rodando antes da parada programada de março", "sugerida"),
                    ("concorrencia", "Avaliando também um fornecedor alemão", "sugerida"),
                    ("autoridade", "Diretor industrial decide; financeiro só valida o fluxo de pagamento", "confirmada"))
    abertos = [n for n in negocios if n.ganho_em is None and n.perdido_em is None]
    for k, (categoria, descricao, status) in enumerate(necessidades):
        negocio = abertos[k % len(abertos)]
        db.add(NecessidadeOportunidade(tenant_id=tenant_id, negocio_id=negocio.id, conta_id=negocio.conta_id, categoria=categoria,
                                       descricao=descricao, citacao=None, fonte_tipo="reuniao", origem="manual", status=status,
                                       criado_por_usuario_id=negocio.vendedor_usuario_id))


def _licitacoes(db: Session, tenant_id: str, usuario_id: int, contas, ofertas) -> None:
    """Bid Intelligence: pregões eletrônicos, RFP privado e oportunidades públicas futuras, cada uma num estágio."""
    agora = _agora()
    L = bids.licitacoes
    itens = (
        {"titulo": "Pregão Eletrônico 90123/2026 — Manutenção preditiva das estações elevatórias",
         "objeto": "Contratação de serviço de manutenção preditiva com sensoriamento IoT de 120 conjuntos motobomba",
         "orgao_nome": "Companhia de Saneamento Rio Manso", "modalidade": "PUBLIC_TENDER", "valor_estimado": 480000.0,
         "conta_id": contas[13].id, "oferta_id": ofertas[3].id, "prazo_proposta": agora + timedelta(days=12),
         "prazo_esclarecimento": agora + timedelta(days=6), "data_publicacao": agora - timedelta(days=3),
         "fonte_url": "https://pncp.demo.invalid/editais/90123-2026", "concorrentes": ["Hidrotec Serviços", "Manutec Brasil"],
         "_status": ["EM_ANALISE"], "_go": None},
        {"titulo": "Pregão Eletrônico SRP 45/2026 — Registro de preços de sensores de vibração",
         "objeto": "Registro de preços para aquisição de sensores sem fio e licenças de monitoramento por 12 meses",
         "orgao_nome": "Prefeitura Municipal de Vale do Sol", "modalidade": "PRICE_REGISTRATION", "valor_estimado": 260000.0,
         "conta_id": contas[12].id, "oferta_id": ofertas[3].id, "prazo_proposta": agora + timedelta(days=20),
         "data_publicacao": agora - timedelta(days=5), "fonte_url": "https://pncp.demo.invalid/editais/45-2026",
         "_status": ["EM_ANALISE"], "_go": ("GO", "Atestados compatíveis e margem adequada")},
        {"titulo": "RFP — Programa de confiabilidade de ativos 2027 (Metalúrgica Horizonte)",
         "objeto": "Proposta para expansão da manutenção preditiva para as plantas de Sorocaba e Betim",
         "orgao_nome": "Metalúrgica Horizonte S.A.", "modalidade": "PRIVATE_RFP", "valor_estimado": 380000.0,
         "conta_id": contas[0].id, "oferta_id": ofertas[0].id, "prazo_proposta": agora + timedelta(days=8),
         "_status": ["EM_ANALISE"], "_go": ("GO", "Cliente atual com satisfação alta"), "_enviar": True},
        {"titulo": "Concorrência 12/2027 — Gestão de ativos da rede municipal de saúde (previsão no PCA)",
         "objeto": "Plataforma de gestão de ativos e manutenção para 38 unidades de saúde — publicação prevista no PCA 2027",
         "orgao_nome": "Secretaria Municipal de Saúde de Vale do Sol", "modalidade": "PUBLIC_TENDER", "valor_estimado": 720000.0,
         "oferta_id": ofertas[3].id, "data_publicacao": agora + timedelta(days=45), "_status": [], "_go": None},
        {"titulo": "Dispensa eletrônica 07/2027 — Diagnóstico energético do Paço Municipal (previsão)",
         "objeto": "Diagnóstico de eficiência energética com relatório para o programa municipal de redução de custos",
         "orgao_nome": "Prefeitura Municipal de Vale do Sol", "modalidade": "DIRECT_AWARD", "valor_estimado": 54000.0,
         "oferta_id": ofertas[2].id, "data_publicacao": agora + timedelta(days=75), "_status": [], "_go": None},
        {"titulo": "Pregão Eletrônico 31/2026 — Manutenção de ar-condicionado hospitalar",
         "objeto": "Manutenção preventiva e corretiva de 140 equipamentos de climatização",
         "orgao_nome": "Hospital Regional do Vale (público)", "modalidade": "PUBLIC_TENDER", "valor_estimado": 190000.0,
         "_status": ["EM_ANALISE"], "_go": ("NO_GO", "Fora do nosso escopo técnico (climatização)")},
        {"titulo": "Pregão Eletrônico 102/2025 — Monitoramento de subestações (encerrado)",
         "objeto": "Monitoramento contínuo de 6 subestações de energia", "orgao_nome": "Companhia de Saneamento Rio Manso",
         "modalidade": "PUBLIC_TENDER", "valor_estimado": 310000.0, "_status": ["EM_ANALISE"],
         "_go": ("GO", "Histórico com o órgão"), "_enviar": True, "_resultado": (True, None, 286000.0, None)},
    )
    requisitos = (("HABILITACAO", "Certidão negativa de débitos federais e trabalhistas"),
                  ("QUALIFICACAO_TECNICA", "Atestado de capacidade técnica com no mínimo 50 equipamentos monitorados"),
                  ("SLA", "Atendimento a alarmes críticos em até 4 horas"), ("GARANTIA", "Garantia de 12 meses para os sensores"),
                  ("REQUISITO_TECNICO", "Painel web com histórico de 24 meses e exportação de dados"))
    for dados in itens:
        corpo = {k: v for k, v in dados.items() if not k.startswith("_")}
        lic = L.criar(db, tenant_id, usuario_id, {**corpo, "responsavel_usuario_id": usuario_id})
        for categoria, descricao in requisitos[: 5 if dados["_status"] else 2]:
            L.criar_requisito_manual(db, tenant_id, usuario_id, lic.id, categoria, descricao, None, None, None, None, obrigatorio=True)
        for status in dados["_status"]:
            L.mudar_status(db, tenant_id, usuario_id, lic.id, status)
        if dados["_go"]:
            L.decidir(db, tenant_id, usuario_id, lic.id, dados["_go"][0], dados["_go"][1])
        if dados.get("_enviar"):
            L.mudar_status(db, tenant_id, usuario_id, lic.id, "PROPOSTA_ENVIADA")
        if dados.get("_resultado"):
            L.registrar_resultado(db, tenant_id, usuario_id, lic.id, *dados["_resultado"])


def semear(db: Session, tenant_id: str, expira_em: datetime, creditos_ia: int) -> Usuario:
    """Preenche o tenant de demonstração; devolve a gestora (usuário da sessão)."""
    usuarios = _equipe(db, tenant_id)
    icps, ofertas = _icps_ofertas(db, tenant_id)
    lista = ListaProspeccao(tenant_id=tenant_id, nome="Indústrias Sul/Sudeste — 4º trimestre", icp_id=icps[0].id,
                            cargos_alvo=["Diretor Industrial", "Gerente de Manutenção"], criado_por_usuario_id=usuarios[3].id)
    db.add(lista)
    db.flush()
    contas, decisores = _contas(db, tenant_id, icps, usuarios[1:], lista)
    negocios = _negocios(db, tenant_id, contas, decisores, ofertas, usuarios)
    _atividades(db, tenant_id, contas, negocios)
    _reunioes(db, tenant_id, contas, decisores, usuarios)
    _prospeccao(db, tenant_id, icps, ofertas, decisores, usuarios)
    _relacionamento(db, tenant_id, contas, decisores, negocios, usuarios)
    db.commit()
    gestora = usuarios[0]
    _licitacoes(db, tenant_id, gestora.id, contas, ofertas)
    demonstracao.semear(db, tenant_id, gestora.id)  # lado comprador (compras públicas e sourcing), atrás da barreira
    finops.carteira.conceder(db, tenant_id, finops.comercial.TipoLote.PROMOTIONAL, Decimal(creditos_ia), "DEMONSTRACAO", expira_em=expira_em,
                             idempotency_key=f"demo-{tenant_id}", descricao="Créditos de IA da demonstração")
    db.commit()
    return gestora
