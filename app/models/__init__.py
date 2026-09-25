from app.models.alerta_detrator import AlertaDetrator
from app.models.aprovacao import Aprovacao
from app.models.atividade import Atividade
from app.models.auditoria import AuditLog
from app.models.cache_mercado_externo import CacheMercadoExterno
from app.models.cadencia import Cadencia
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.conta import Conta
from app.models.conta_franquia_consumo import ContaFranquiaConsumo
from app.models.configuracao_agente_corporativo import ConfiguracaoAgenteCorporativo
from app.models.configuracao_canal import ConfiguracaoCanal
from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp
from app.models.custo_aquisicao import CustoAquisicao
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.models.configuracao_notificacao import ConfiguracaoNotificacao
from app.models.configuracao_nps import ConfiguracaoNps
from app.models.configuracao_painel import ConfiguracaoPainel
from app.models.configuracao_qualificacao import ConfiguracaoQualificacao
from app.models.convite_cadastro import ConviteCadastro
from app.models.convite_vitrine import ConviteVitrine
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.email_direto import EmailDireto
from app.models.email_recebido import EmailRecebido
from app.models.descarte_conta import DescarteConta
from app.models.enriquecimento_semanal_consumo import EnriquecimentoSemanalConsumo
from app.models.estagio_funil import EstagioFunil
from app.models.faq_item import FaqItem
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.models.icp import ICP
from app.models.indicacao import Indicacao
from app.models.intent import Intent
from app.models.interacao_conta import InteracaoConta
from app.models.interacao_tenant import InteracaoTenant
from app.models.licenca import Licenca
from app.models.lista_prospeccao import ListaProspeccao
from app.models.material_oferta import MaterialOferta
from app.models.mensagem import Mensagem
from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.negocio import Negocio
from app.models.notificacao_rede_social import NotificacaoRedeSocial
from app.models.notificacao_vendedor import NotificacaoVendedor
from app.models.oferta import Oferta
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.pausa_canal import PausaCanal
from app.models.perfil_empresa import PerfilEmpresa
from app.models.pergunta_agente_corporativo import PerguntaAgenteCorporativo
from app.models.pesquisa_nps import PesquisaNps
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.evento_dominio import EventoDominio
from app.models.conhecimento_corporativo import ConhecimentoCorporativo
from app.models.perfil_inteligencia import PerfilInteligencia
from app.models.evento_aprendizado import EventoAprendizado
from app.models.chave_api_tenant import ChaveApiTenant
from app.models.registro_idempotencia import RegistroIdempotencia
from app.models.assinatura_webhook_tenant import AssinaturaWebhookTenant
from app.models.entrega_webhook import EntregaWebhook
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.execucao_sync import ExecucaoSync
from app.models.plano import Plano
from app.models.proposta_negocio import PropostaNegocio
from app.models.template_proposta import ItemTemplateProposta, TemplateProposta
from app.models.qualificacao import QualificacaoScore
from app.models.recorte_cnpj_estado import RecorteCnpjEstado
from app.models.registro_envio_diario import RegistroEnvioDiario
from app.models.registro_reputacao_canal import RegistroReputacaoCanal
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente
from app.models.registro_tratamento import RegistroTratamento
from app.models.regra_aprendida import RegraAprendida
from app.models.regra_auto_aprovacao import RegraAutoAprovacao
from app.models.registro_oportunidade import RegistroOportunidade
from app.models.reuniao import Reuniao
from app.models.rotulo_tipo_tenant import RotuloTipoTenant
from app.models.sala_corporativa import SalaCorporativa
from app.models.sala_compra import SalaCompra
from app.models.canal_sala import CanalSala
from app.models.mensagem_sala import MensagemSala
from app.models.solicitacao_desconto import SolicitacaoDesconto
from app.models.tarefa_linkedin import TarefaLinkedin
from app.models.template_whatsapp import TemplateWhatsApp
from app.models.tenant import Tenant
from app.models.toque_cadencia import ToqueCadencia
from app.models.comentario_post import ComentarioPost
from app.models.midia_post import MidiaPost
from app.models.post_rede_social import PostRedeSocial
from app.models.reacao_post import ReacaoPost
from app.models.redefinicao_senha import RedefinicaoSenha
from app.models.relacionamento_empresarial import RelacionamentoEmpresarial
from app.models.seguidor_empresa import SeguidorEmpresa
from app.models.sinal_oportunidade import SinalOportunidade
from app.models.turno_conversa import TurnoConversa
from app.models.usuario import Usuario
from app.models.verificacao_empresa import VerificacaoEmpresa
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento, CnpjSocio

__all__ = [
    "ICP",
    "Oferta",
    "MaterialOferta",
    "ConfiguracaoComunicacao",
    "ConfiguracaoEnvio",
    "ConfiguracaoWhatsApp",
    "ConfiguracaoEmailSmtp",
    "ConfiguracaoCanal",
    "ConfiguracaoQualificacao",
    "ConfiguracaoNotificacao",
    "ConfiguracaoPainel",
    "ConfiguracaoNps",
    "Conta",
    "CampoEnriquecido",
    "ContaFranquiaConsumo",
    "EnriquecimentoSemanalConsumo",
    "DescarteConta",
    "Decisor",
    "Cadencia",
    "Campanha",
    "CampanhaDestinatario",
    "ToqueCadencia",
    "Mensagem",
    "TemplateWhatsApp",
    "TarefaLinkedin",
    "RegistroEnvioDiario",
    "RegistroReputacaoCanal",
    "PausaCanal",
    "Aprovacao",
    "RegraAutoAprovacao",
    "RegraAprendida",
    "AuditLog",
    "RegistroTratamento",
    "RegistroSupressaoPermanente",
    "QualificacaoScore",
    "ConversaQualificacao",
    "TurnoConversa",
    "NotificacaoVendedor",
    "Reuniao",
    "FaqItem",
    "PesquisaNps",
    "AlertaDetrator",
    "Indicacao",
    "Tenant",
    "RotuloTipoTenant",
    "Plano",
    "Licenca",
    "ListaProspeccao",
    "PagamentoLicenca",
    "Usuario",
    "ConviteCadastro",
    "ConviteVitrine",
    "EstagioFunil",
    "Negocio",
    "Atividade",
    "PropostaNegocio",
    "TemplateProposta",
    "ItemTemplateProposta",
    "CustoAquisicao",
    "PerfilEmpresa",
    "ConexaoEmpresa",
    "VerificacaoEmpresa",
    "RelacionamentoEmpresarial",
    "SeguidorEmpresa",
    "PostRedeSocial",
    "MidiaPost",
    "ComentarioPost",
    "ReacaoPost",
    "RedefinicaoSenha",
    "NotificacaoRedeSocial",
    "Intent",
    "SinalOportunidade",
    "SalaCorporativa",
    "SalaCompra",
    "CanalSala",
    "MensagemSala",
    "MensagemRedeSocial",
    "InteracaoTenant",
    "InteracaoConta",
    "CnpjEstabelecimento",
    "CnpjSocio",
    "RecorteCnpjEstado",
    "FilaEnriquecimentoConta",
    "RegistroOportunidade",
    "SolicitacaoDesconto",
    "ConfiguracaoAgenteCorporativo",
    "PerguntaAgenteCorporativo",
    "RegistroUsoIa",
    "EventoDominio",
    "ConhecimentoCorporativo",
    "PerfilInteligencia",
    "EventoAprendizado",
    "ChaveApiTenant",
    "RegistroIdempotencia",
    "AssinaturaWebhookTenant",
    "EntregaWebhook",
    "ConexaoIntegracao",
    "ExecucaoSync",
    "CacheMercadoExterno",
    "EmailDireto",
    "EmailRecebido",
]
