from app.models.alerta_detrator import AlertaDetrator
from app.models.aprovacao import Aprovacao
from app.models.atividade import Atividade
from app.models.auditoria import AuditLog
from app.models.cadencia import Cadencia
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.campo_enriquecido import CampoEnriquecido
from app.models.conexao_empresa import ConexaoEmpresa
from app.models.conexao_linkedin import ConexaoLinkedin
from app.models.conta import Conta
from app.models.conta_franquia_consumo import ContaFranquiaConsumo
from app.models.configuracao_canal import ConfiguracaoCanal
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
from app.models.descarte_conta import DescarteConta
from app.models.estagio_funil import EstagioFunil
from app.models.faq_item import FaqItem
from app.models.icp import ICP
from app.models.indicacao import Indicacao
from app.models.interacao_conta import InteracaoConta
from app.models.interacao_tenant import InteracaoTenant
from app.models.licenca import Licenca
from app.models.material_oferta import MaterialOferta
from app.models.mensagem import Mensagem
from app.models.mensagem_rede_social import MensagemRedeSocial
from app.models.negocio import Negocio
from app.models.notificacao_vendedor import NotificacaoVendedor
from app.models.oferta import Oferta
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.pausa_canal import PausaCanal
from app.models.perfil_empresa import PerfilEmpresa
from app.models.pesquisa_nps import PesquisaNps
from app.models.plano import Plano
from app.models.proposta_negocio import PropostaNegocio
from app.models.template_proposta import ItemTemplateProposta, TemplateProposta
from app.models.qualificacao import QualificacaoScore
from app.models.registro_envio_diario import RegistroEnvioDiario
from app.models.registro_reputacao_canal import RegistroReputacaoCanal
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente
from app.models.registro_tratamento import RegistroTratamento
from app.models.regra_auto_aprovacao import RegraAutoAprovacao
from app.models.reuniao import Reuniao
from app.models.tarefa_linkedin import TarefaLinkedin
from app.models.template_whatsapp import TemplateWhatsApp
from app.models.tenant import Tenant
from app.models.toque_cadencia import ToqueCadencia
from app.models.turno_conversa import TurnoConversa
from app.models.usuario import Usuario
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento, CnpjSocio

__all__ = [
    "ICP",
    "Oferta",
    "MaterialOferta",
    "ConfiguracaoComunicacao",
    "ConfiguracaoEnvio",
    "ConfiguracaoWhatsApp",
    "ConfiguracaoCanal",
    "ConfiguracaoQualificacao",
    "ConfiguracaoNotificacao",
    "ConfiguracaoPainel",
    "ConfiguracaoNps",
    "Conta",
    "CampoEnriquecido",
    "ContaFranquiaConsumo",
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
    "Plano",
    "Licenca",
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
    "MensagemRedeSocial",
    "InteracaoTenant",
    "InteracaoConta",
    "CnpjEstabelecimento",
    "CnpjSocio",
]
