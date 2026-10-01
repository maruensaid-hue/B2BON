/** MAP Performance Comercial (D-080): tipos e formatação. Nenhum alvo, taxa ou quota fica no frontend — tudo vem da
 * política e das quotas versionadas no backend. */

export interface Alerta {
  codigo: string;
  severidade: "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";
  mensagem: string;
  acao: string;
  evidencias: { id: number; nome: string; conta: string; valor: number; dias_sem_acao: number }[];
}

export interface MetaAtividade {
  realizado: number;
  alvo: number;
  pct: number | null;
}

export interface Funil {
  contas_trabalhadas: number;
  contatos_efetivos: number;
  reunioes: number;
  oportunidades_qualificadas: number;
  propostas: number;
  fechamentos: number;
  follow_ups: number;
  valor_fechado: number;
}

export interface Campanha {
  codigo: string;
  nome: string;
  situacao: string;
  meta: number;
  new_mrr: number;
  attainment: number;
  faixa_bonus: number;
  base_comissao_novas_vendas: number;
  elegivel: boolean;
  motivos_inelegibilidade: string[];
  bonus: number;
  status_bonus: string;
  vendas_por_mes: Record<string, number>;
}

export interface Taxa {
  baseline: number;
  observada: number | null;
  amostra: number;
  recomendada: number;
  fonte: "OBSERVED" | "BASELINE";
}

export interface PainelIndividual {
  representante: { id: number; nome: string; vinculado_crm: boolean };
  competencia: string;
  quota: number | null;
  realizado_new_mrr: number;
  attainment: number | null;
  gap: number | null;
  pipeline: { qualificado_mrr: number; ponderado_mrr: number; alvo: number | null; multiplo_alvo: number; cobertura: number | null;
    negocios: number; atualizadas_pct: number | null };
  forecast_new_mrr: number;
  fechado_crm_mrr: number | null;
  ticket_medio: number | null;
  ticket_medio_baseline: number;
  mix: { por_familia: Record<string, { valor: number; participacao: number | null; alvo: number | null }>;
    alto_valor_participacao: number | null; alto_valor_minimo: number; mix_quality: string | null };
  funil_mes: Funil | null;
  taxas_mes: Record<string, number | null> | null;
  atividade: { dia: Record<string, MetaAtividade> | null; semana: Record<string, MetaAtividade> | null };
  velocidade: Record<string, { negocios: number; pipeline_mrr: number; dias_padrao: number; ciclo_medio_observado: number | null;
    pipeline_governo_tcv?: number }>;
  comissao: { realizada: number; a_receber: number; retida_inadimplencia: number; aguardando_parametros: number; taxa: number;
    por_competencia: Record<string, number> };
  carteira: Record<string, number>;
  governo: { qualificadas: number; pipeline_qualificado: number; pipeline_licenca: number; pipeline_assinatura_anual: number;
    novas_qualificadas_semana: number; meta_semana: number; bookings_mes: number;
    proximos_fechamentos: { id: number; titulo: string; entidade: string; estagio: string; fechamento_previsto: string }[] };
  campanhas: Campanha[];
  alertas: Alerta[];
  pendencias: string[];
  negocios_abertos: { id: number; nome: string; conta: string; valor: number; probabilidade: number; estagio: string; familia: string;
    velocidade: string; fechamento_previsto: string; dias_sem_acao: number; proximo_passo: string | null }[];
  aprendizado: Record<string, Taxa>;
}

export interface LinhaEquipe {
  representante: { id: number; nome: string; vinculado_crm: boolean };
  quota: number | null;
  realizado_new_mrr: number;
  attainment: number | null;
  gap: number | null;
  cobertura: number | null;
  forecast_new_mrr: number;
  ticket_medio: number | null;
  mix_quality: string | null;
  atividade_semana_pct: Record<string, number | null>;
  oportunidades_atualizadas_pct: number | null;
  governo_pipeline_qualificado: number;
  governo_novas_semana: number;
  comissao_a_receber: number;
  alertas: Alerta[];
  pendencias: string[];
}

export interface ResumoEquipe {
  representantes: number;
  quota: number;
  realizado_new_mrr: number;
  attainment: number | null;
  gap: number;
  pipeline_mrr: number;
  cobertura: number | null;
  forecast_new_mrr: number;
  governo_pipeline_qualificado: number;
}

export interface PainelEquipe {
  competencia: string;
  configuracao_pendente: string[];
  equipe: ResumoEquipe;
  representantes: LinhaEquipe[];
  excecoes: LinhaEquipe[];
  aprendizado: Record<string, Taxa>;
}

export interface Daily {
  data: string;
  configuracao_pendente: string[];
  competencia: string;
  equipe: ResumoEquipe;
  sem_intervencao: number;
  intervencoes: {
    representante: { id: number; nome: string };
    attainment: number | null;
    gap: number | null;
    forecast_new_mrr: number;
    cobertura: number | null;
    alertas: Alerta[];
    pendencias: string[];
    negocios_que_destravam: { id: number; nome: string; conta: string; valor: number; probabilidade: number; fechamento_previsto: string;
      proximo_passo: string }[];
    proximas_acoes: string[];
  }[];
}

export interface Quota {
  id: number;
  representante_id: number | null;
  competencia: string;
  valor: number;
  multiplo_cobertura: number | null;
  pipeline_alvo: number | null;
  versao: number;
  motivo: string | null;
}

export interface Prontidao {
  representantes_ativos: number;
  vinculados: number;
  sem_vinculo: { id: number; nome: string }[];
  tenants_crm: string[];
  ofertas: { id: number; nome: string; tenant_id: string; familia: string | null }[];
  ofertas_sem_familia: { id: number; nome: string }[];
  tipos_contato_efetivo: string[];
  contato_efetivo_confirmado: boolean;
  pendencias: string[];
  pronto: boolean;
}

export interface UsuarioCrm {
  id: number;
  nome: string;
  email: string;
  tenant_id: string;
  vinculado_a: string | null;
}

export const ROTULOS_TIPO_ATIVIDADE: Record<string, string> = {
  ligacao: "Ligação",
  reuniao: "Reunião",
  email: "E-mail",
  whatsapp: "WhatsApp",
  linkedin: "LinkedIn",
  nota: "Nota",
  tarefa: "Tarefa",
};

export interface Configuracao {
  prontidao: Prontidao;
  familias: string[];
  tipos_atividade: string[];
  performance: { versao: number; regras: Record<string, unknown> };
  comissao_privada: { versao: number; regras: Record<string, unknown> };
  campanhas: { codigo: string; versao: number; regras: Record<string, unknown> }[];
  quotas: Quota[];
  representantes: { id: number; nome: string; usuario_id: number | null }[];
}

export const brl = (valor: number | null | undefined) =>
  valor == null ? "—" : valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export const pct = (valor: number | null | undefined) => (valor == null ? "—" : `${Math.round(valor * 100)}%`);

export const vezes = (valor: number | null | undefined) => (valor == null ? "—" : `${valor.toFixed(1)}x`);

export const competenciaAtual = () => new Date().toISOString().slice(0, 7);

export const ROTULOS_ATIVIDADE: Record<string, string> = {
  contas_trabalhadas: "Contas trabalhadas",
  contatos_efetivos: "Contatos efetivos",
  reunioes: "Reuniões",
  follow_ups: "Follow-ups",
  oportunidades_qualificadas: "Oportunidades qualificadas",
  propostas: "Propostas",
  fechamentos: "Fechamentos",
};

export const ROTULOS_ETAPA: Record<string, string> = {
  contato_efetivo: "Conta → contato",
  reuniao: "Contato → reunião",
  oportunidade_qualificada: "Reunião → oportunidade",
  proposta: "Oportunidade → proposta",
  fechamento: "Proposta → fechamento",
};

export const toneSeveridade = (severidade: Alerta["severidade"]) =>
  severidade === "CRITICAL" ? "red" : severidade === "HIGH" ? "amber" : severidade === "MEDIUM" ? "violet" : "muted";

export const toneAttainment = (valor: number | null) =>
  valor == null ? "text-muted" : valor >= 1 ? "text-green" : valor >= 0.8 ? "text-amber" : "text-red";
