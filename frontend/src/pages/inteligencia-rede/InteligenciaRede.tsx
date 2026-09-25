import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { TutorialInteligenciaRede } from "@/pages/inteligencia-rede/TutorialInteligenciaRede";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface IcpResumo {
  id: number;
  nome: string;
}

interface FitIcpRede {
  tenant_id_candidato: string;
  empresa_nome: string;
  fit_score: number;
  matched_icp: string;
  reasons: string[];
  missing_data: string[];
  confidence: "alta" | "media" | "baixa";
}

interface IntentResumo {
  id: number;
  titulo: string;
  empresa_nome: string;
}

interface MatchIntent {
  tenant_id_candidato: string;
  empresa_nome: string;
  match_score: number;
  match_reasons: string[];
  confidence: "alta" | "media" | "baixa";
  signals: string[];
}

const ROTULO_CONFIANCA: Record<string, { texto: string; tone: "green" | "amber" | "muted" }> = {
  alta: { texto: "Confiança alta", tone: "green" },
  media: { texto: "Confiança média", tone: "amber" },
  baixa: { texto: "Confiança baixa", tone: "muted" },
};

interface SinalOportunidade {
  id: number;
  tenant_id_alvo: string;
  empresa_nome: string;
  tipo_sinal: "fit_icp" | "match_intent" | "relacionamento_declarado";
  score: number;
  confianca: "alta" | "media" | "baixa";
  motivo: string;
  evidencias: string[];
  status: "novo" | "visto" | "descartado" | "convertido";
  conta_id_gerada: number | null;
  criado_em: string;
}

const ROTULO_TIPO_SINAL: Record<string, string> = {
  fit_icp: "Fit de ICP",
  match_intent: "Match de necessidade",
  relacionamento_declarado: "Relacionamento declarado",
};

const ROTULO_STATUS_SINAL: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  novo: { texto: "Novo", tone: "green" },
  visto: { texto: "Visto", tone: "muted" },
  descartado: { texto: "Descartado", tone: "red" },
  convertido: { texto: "Convertido em conta", tone: "amber" },
};

interface SaudeRelacionamento {
  tenant_id_alvo: string;
  empresa_nome: string;
  dias_sem_interacao: number | null;
  tem_relacionamento_declarado: boolean;
  classificacao: "aquecido" | "neutro" | "esfriando" | "sem_interacao";
  sugestoes: string[];
}

const ROTULO_CLASSIFICACAO_SAUDE: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  aquecido: { texto: "Aquecido", tone: "green" },
  neutro: { texto: "Neutro", tone: "amber" },
  esfriando: { texto: "Esfriando", tone: "red" },
  sem_interacao: { texto: "Sem interação ainda", tone: "muted" },
};

interface RiscoPipeline {
  negocio_id: number;
  negocio_nome: string;
  conta_id: number;
  conta_nome: string | null;
  dias_sem_atividade: number;
  tem_decision_maker: boolean;
  riscos: string[];
}

interface AtribuicaoReceita {
  contas_geradas_pela_rede: number;
  negocios_em_aberto_valor: number;
  negocios_ganhos_valor: number;
  sinais_gerados: number;
  sinais_convertidos: number;
  taxa_conversao_sinais: number;
}

interface SugestaoExpansao {
  conta_id: number;
  conta_nome: string;
  oferta_id: number;
  oferta_nome: string;
  motivo: string;
}

const FORMATADOR_MOEDA = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function InteligenciaRede() {
  const { usuario, marcarTutorialModuloVisto } = useAuth();
  // Tutorial do módulo (raio-X 2026-09-21) — abre sozinho na primeira
  // visita, coexiste com o tour grande.
  const [tutorialAberto, setTutorialAberto] = useState(false);
  const [carregado, setCarregado] = useState(false);
  useEffect(() => {
    if (usuario && carregado && !(usuario.tutoriais_modulo_vistos ?? []).includes("inteligencia-rede")) {
      setTutorialAberto(true);
    }
  }, [usuario, carregado]);
  function fecharTutorial() {
    setTutorialAberto(false);
    if (usuario && !(usuario.tutoriais_modulo_vistos ?? []).includes("inteligencia-rede")) {
      marcarTutorialModuloVisto("inteligencia-rede");
    }
  }
  const [icps, setIcps] = useState<IcpResumo[]>([]);
  const [icpSelecionado, setIcpSelecionado] = useState<string>("");
  const [fits, setFits] = useState<FitIcpRede[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [intents, setIntents] = useState<IntentResumo[]>([]);
  const [intentSelecionada, setIntentSelecionada] = useState<string>("");
  const [matches, setMatches] = useState<MatchIntent[]>([]);
  const [carregandoMatches, setCarregandoMatches] = useState(false);
  const [explicandoId, setExplicandoId] = useState<string | null>(null);
  const [explicacoes, setExplicacoes] = useState<Record<string, string>>({});
  const [sinais, setSinais] = useState<SinalOportunidade[]>([]);
  const [gerandoSinais, setGerandoSinais] = useState(false);
  const [convertendoId, setConvertendoId] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [saudeRelacionamentos, setSaudeRelacionamentos] = useState<SaudeRelacionamento[]>([]);
  const [riscosPipeline, setRiscosPipeline] = useState<RiscoPipeline[]>([]);
  const [atribuicaoReceita, setAtribuicaoReceita] = useState<AtribuicaoReceita | null>(null);
  const [sugestoesExpansao, setSugestoesExpansao] = useState<SugestaoExpansao[]>([]);

  useEffect(() => {
    Promise.allSettled([
      api
        .get<SinalOportunidade[]>("/inteligencia-rede/sinais")
        .then(setSinais)
        .catch(() => setErro("Não foi possível carregar os sinais de oportunidade.")),
      api
        .get<SaudeRelacionamento[]>("/inteligencia-rede/saude-relacionamentos")
        .then(setSaudeRelacionamentos)
        .catch(() => setErro("Não foi possível carregar a saúde dos relacionamentos.")),
      api
        .get<RiscoPipeline[]>("/inteligencia-rede/riscos-pipeline")
        .then(setRiscosPipeline)
        .catch(() => setErro("Não foi possível carregar os riscos de pipeline.")),
      api
        .get<AtribuicaoReceita>("/inteligencia-rede/atribuicao-receita")
        .then(setAtribuicaoReceita)
        .catch(() => setErro("Não foi possível carregar a atribuição de receita.")),
      api
        .get<SugestaoExpansao[]>("/inteligencia-rede/sugestoes-expansao")
        .then(setSugestoesExpansao)
        .catch(() => setErro("Não foi possível carregar as sugestões de expansão.")),
    ]).then(() => setCarregado(true));
  }, []);

  useEffect(() => {
    api
      .get<IcpResumo[]>("/icp")
      .then((resposta) => {
        setIcps(resposta);
        if (resposta.length > 0) setIcpSelecionado(String(resposta[0].id));
      })
      .catch(() => setErro("Não foi possível carregar os ICPs."));
    api
      .get<IntentResumo[]>("/rede-social/intents")
      .then((resposta) => {
        setIntents(resposta);
        if (resposta.length > 0) setIntentSelecionada(String(resposta[0].id));
      })
      .catch(() => setErro("Não foi possível carregar as necessidades da rede."));
  }, []);

  useEffect(() => {
    if (!icpSelecionado) {
      setFits([]);
      return;
    }
    setCarregando(true);
    setErro(null);
    api
      .get<FitIcpRede[]>(`/inteligencia-rede/fit-icp?icp_id=${icpSelecionado}`)
      .then(setFits)
      .catch((error) => setErro(error instanceof ApiError ? error.message : "Não foi possível calcular o fit."))
      .finally(() => setCarregando(false));
  }, [icpSelecionado]);

  useEffect(() => {
    if (!intentSelecionada) {
      setMatches([]);
      return;
    }
    setCarregandoMatches(true);
    setErro(null);
    api
      .get<MatchIntent[]>(`/inteligencia-rede/intents/${intentSelecionada}/matches`)
      .then(setMatches)
      .catch((error) => setErro(error instanceof ApiError ? error.message : "Não foi possível calcular os matches."))
      .finally(() => setCarregandoMatches(false));
  }, [intentSelecionada]);

  async function explicarComIA(tenantIdCandidato: string) {
    if (explicandoId !== null) return;
    setExplicandoId(tenantIdCandidato);
    try {
      const resposta = await api.post<{ explicacao: string }>(
        `/inteligencia-rede/intents/${intentSelecionada}/matches/${tenantIdCandidato}/explicar-com-ia`,
      );
      setExplicacoes((atual) => ({ ...atual, [tenantIdCandidato]: resposta.explicacao }));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar a explicação com IA.");
    } finally {
      setExplicandoId(null);
    }
  }

  async function gerarSinais() {
    if (gerandoSinais) return;
    setGerandoSinais(true);
    setErro(null);
    try {
      setSinais(await api.post<SinalOportunidade[]>("/inteligencia-rede/sinais/gerar"));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar os sinais de oportunidade.");
    } finally {
      setGerandoSinais(false);
    }
  }

  async function descartarSinal(sinalId: number) {
    try {
      const atualizado = await api.post<SinalOportunidade>(`/inteligencia-rede/sinais/${sinalId}/descartar`);
      setSinais((atual) => atual.map((sinal) => (sinal.id === sinalId ? atualizado : sinal)));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível descartar este sinal.");
    }
  }

  async function converterSinal(sinalId: number) {
    if (convertendoId !== null) return;
    setConvertendoId(sinalId);
    setAviso(null);
    try {
      const resultado = await api.post<{
        conta_id: number;
        negocio_id: number | null;
        conta_reaproveitada: boolean;
        negocio_reaproveitado: boolean;
      }>(`/inteligencia-rede/sinais/${sinalId}/converter`);
      setSinais(await api.get<SinalOportunidade[]>("/inteligencia-rede/sinais"));
      // Fase 8: a conversão reaproveita conta e negócio existentes (sem duplicar).
      const conta = resultado.conta_reaproveitada ? `Conta #${resultado.conta_id} já existente` : `Conta #${resultado.conta_id} criada`;
      const negocio =
        resultado.negocio_id === null
          ? " como lead de prospecção"
          : resultado.negocio_reaproveitado
            ? `, vinculada ao negócio aberto #${resultado.negocio_id}`
            : ` e negócio #${resultado.negocio_id} aberto no CRM`;
      setAviso(`${conta}${negocio} — escolha o decisor no CRM para seguir.`);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível converter este sinal em conta.");
    } finally {
      setConvertendoId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="font-head text-[22px] font-extrabold text-text">Sinais de Oportunidade</h1>
          <button type="button" onClick={() => setTutorialAberto(true)} className="text-[11px] text-muted hover:text-cyan">
            🔄 Rever tutorial
          </button>
        </div>
        <p className="text-[13px] text-muted">Inteligência comercial cruzando ICP, Intents e o Business Graph da rede</p>
      </div>

      {erro && <div className="rounded-lg border border-red/30 bg-red/10 p-3 text-[12px] text-red">{erro}</div>}
      {aviso && <div className="rounded-lg border border-cyan/30 bg-cyan/10 p-3 text-[12px] text-cyan">{aviso}</div>}

      <Card data-tutorial-id="inteligencia-rede:fit-icp">
        <SectionLabel>Fit por ICP na Rede</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Compara seu ICP contra o perfil público de todas as outras empresas do Shoal — quanto mais critérios
          baterem (CNAE, UF, porte), maior o fit. Sempre com os motivos explicados, nunca um score isolado.
        </p>
        {icps.length === 0 ? (
          <div className="text-[12px] text-muted">Cadastre um ICP em Prospecção antes de calcular fit com a rede.</div>
        ) : (
          <div className="mb-3 w-[280px]">
            <Select value={icpSelecionado} onChange={(event) => setIcpSelecionado(event.target.value)}>
              {icps.map((icp) => (
                <option key={icp.id} value={icp.id}>
                  {icp.nome}
                </option>
              ))}
            </Select>
          </div>
        )}
        <div className="flex flex-col gap-2">
          {carregando && <div className="text-[12px] text-muted">Calculando...</div>}
          {!carregando &&
            fits.map((fit) => {
              const confianca = ROTULO_CONFIANCA[fit.confidence] ?? ROTULO_CONFIANCA.baixa;
              return (
                <div key={fit.tenant_id_candidato} className="rounded-lg border border-border p-3 text-[12px]">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-text">{fit.empresa_nome}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={confianca.tone}>{confianca.texto}</Badge>
                      <span className="font-semibold text-cyan">{Math.round(fit.fit_score * 100)}% fit</span>
                    </div>
                  </div>
                  {fit.reasons.length > 0 && (
                    <ul className="list-disc pl-4 text-text">
                      {fit.reasons.map((motivo) => (
                        <li key={motivo}>{motivo}</li>
                      ))}
                    </ul>
                  )}
                  {fit.missing_data.length > 0 && (
                    <div className="mt-1 text-muted">
                      Dados que a empresa não preencheu: {fit.missing_data.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          {!carregando && icpSelecionado && fits.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma outra empresa da rede ainda.</div>
          )}
        </div>
      </Card>

      <Card>
        <SectionLabel>Fornecedores sugeridos para uma Necessidade</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Compara uma necessidade declarada na rede contra o que cada empresa oferece (produtos, mercados,
          tecnologias), somando pontos quando já existe conexão ou relacionamento comercial declarado entre as
          empresas. Sempre com os motivos explicados.
        </p>
        {intents.length === 0 ? (
          <div className="text-[12px] text-muted">
            Publique ou aguarde uma necessidade no Shoal antes de calcular fornecedores sugeridos.
          </div>
        ) : (
          <div className="mb-3 w-[320px]">
            <Select value={intentSelecionada} onChange={(event) => setIntentSelecionada(event.target.value)}>
              {intents.map((intent) => (
                <option key={intent.id} value={intent.id}>
                  {intent.titulo} · {intent.empresa_nome}
                </option>
              ))}
            </Select>
          </div>
        )}
        <div className="flex flex-col gap-2">
          {carregandoMatches && <div className="text-[12px] text-muted">Calculando...</div>}
          {!carregandoMatches &&
            matches.map((match) => {
              const confianca = ROTULO_CONFIANCA[match.confidence] ?? ROTULO_CONFIANCA.baixa;
              return (
                <div key={match.tenant_id_candidato} className="rounded-lg border border-border p-3 text-[12px]">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-text">{match.empresa_nome}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={confianca.tone}>{confianca.texto}</Badge>
                      <span className="font-semibold text-cyan">{Math.round(match.match_score * 100)}% match</span>
                    </div>
                  </div>
                  {(match.match_reasons.length > 0 || match.signals.length > 0) && (
                    <ul className="list-disc pl-4 text-text">
                      {[...match.match_reasons, ...match.signals].map((motivo) => (
                        <li key={motivo}>{motivo}</li>
                      ))}
                    </ul>
                  )}
                  {explicacoes[match.tenant_id_candidato] ? (
                    <div className="mt-2 rounded-md bg-surf2 p-2 text-text">
                      ✨ {explicacoes[match.tenant_id_candidato]}
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => explicarComIA(match.tenant_id_candidato)}
                      disabled={explicandoId === match.tenant_id_candidato}
                      className="mt-2 text-cyan"
                    >
                      {explicandoId === match.tenant_id_candidato ? "Gerando..." : "✨ Explicar com IA"}
                    </button>
                  )}
                </div>
              );
            })}
          {!carregandoMatches && intentSelecionada && matches.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma empresa da rede tem critério ou sinal em comum ainda.</div>
          )}
        </div>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Sinais de Oportunidade</SectionLabel>
          <Button size="sm" data-tutorial-id="inteligencia-rede:atualizar-sinais" onClick={gerarSinais} disabled={gerandoSinais}>
            {gerandoSinais ? "Atualizando..." : "Atualizar sinais"}
          </Button>
        </div>
        <p className="mb-3 text-[12px] text-muted">
          Opportunity Agent: combina fit de ICP, matches de necessidades e relacionamentos declarados no Business
          Graph em um sinal por empresa — gerado sob demanda, nunca automaticamente em segundo plano.
        </p>
        <div className="flex flex-col gap-2">
          {sinais.map((sinal) => {
            const status = ROTULO_STATUS_SINAL[sinal.status] ?? ROTULO_STATUS_SINAL.novo;
            return (
              <div key={sinal.id} className="rounded-lg border border-border p-3 text-[12px]">
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-text">{sinal.empresa_nome}</span>
                    <span className="text-muted">· {ROTULO_TIPO_SINAL[sinal.tipo_sinal] ?? sinal.tipo_sinal}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={status.tone}>{status.texto}</Badge>
                    <span className="font-semibold text-cyan">{Math.round(sinal.score * 100)}%</span>
                  </div>
                </div>
                <div className="text-text">{sinal.motivo}</div>
                {sinal.status !== "convertido" && sinal.status !== "descartado" && (
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" onClick={() => converterSinal(sinal.id)} disabled={convertendoId === sinal.id}>
                      {convertendoId === sinal.id ? "Convertendo..." : "Criar oportunidade"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => descartarSinal(sinal.id)}>
                      Descartar
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
          {sinais.length === 0 && (
            <div className="text-[12px] text-muted">
              Nenhum sinal gerado ainda — clique em "Atualizar sinais" para calcular.
            </div>
          )}
        </div>
      </Card>

      <Card data-tutorial-id="inteligencia-rede:saude-relacionamentos">
        <SectionLabel>Saúde dos Relacionamentos</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Relationship Agent: cruza a última interação (mensagem direta ou sala corporativa) com a existência de um
          relacionamento comercial declarado, pra cada conexão aceita da rede.
        </p>
        <div className="flex flex-col gap-2">
          {saudeRelacionamentos.map((saude) => {
            const classificacao = ROTULO_CLASSIFICACAO_SAUDE[saude.classificacao] ?? ROTULO_CLASSIFICACAO_SAUDE.neutro;
            return (
              <div key={saude.tenant_id_alvo} className="rounded-lg border border-border p-3 text-[12px]">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-semibold text-text">{saude.empresa_nome}</span>
                  <div className="flex items-center gap-2">
                    <Badge tone={classificacao.tone}>{classificacao.texto}</Badge>
                    {saude.dias_sem_interacao !== null && (
                      <span className="text-muted">{saude.dias_sem_interacao}d sem interação</span>
                    )}
                  </div>
                </div>
                {saude.sugestoes.length > 0 && (
                  <ul className="list-disc pl-4 text-text">
                    {saude.sugestoes.map((sugestao) => (
                      <li key={sugestao}>{sugestao}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
          {saudeRelacionamentos.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma conexão aceita na rede ainda.</div>
          )}
        </div>
      </Card>

      <Card>
        <SectionLabel>Riscos de Pipeline</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Pipeline Agent: negócios em aberto sem atividade recente, sem decisor com papel de decisão confirmado, ou
          sem próximo passo definido para a conta.
        </p>
        <div className="flex flex-col gap-2">
          {riscosPipeline.map((risco) => (
            <div key={risco.negocio_id} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-semibold text-text">{risco.negocio_nome}</span>
                <div className="flex items-center gap-2">
                  {risco.conta_nome && <span className="text-muted">{risco.conta_nome}</span>}
                  <Badge tone="red">{risco.dias_sem_atividade}d sem atividade</Badge>
                </div>
              </div>
              <ul className="list-disc pl-4 text-text">
                {risco.riscos.map((motivo) => (
                  <li key={motivo}>{motivo}</li>
                ))}
              </ul>
            </div>
          ))}
          {riscosPipeline.length === 0 && (
            <div className="text-[12px] text-muted">Nenhum negócio em aberto com risco identificado.</div>
          )}
        </div>
      </Card>

      <Card>
        <SectionLabel>Atribuição de Receita da Rede</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Revenue Agent: quanto do seu pipeline nasceu de um sinal de oportunidade convertido em conta, e qual a taxa
          de conversão real dos sinais gerados.
        </p>
        {atribuicaoReceita && (
          <div className="grid grid-cols-2 gap-3 text-[12px] sm:grid-cols-3">
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Contas geradas pela rede</div>
              <div className="font-head text-[18px] font-extrabold text-text">
                {atribuicaoReceita.contas_geradas_pela_rede}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Em aberto</div>
              <div className="font-head text-[18px] font-extrabold text-text">
                {FORMATADOR_MOEDA.format(atribuicaoReceita.negocios_em_aberto_valor)}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Ganho</div>
              <div className="font-head text-[18px] font-extrabold text-green">
                {FORMATADOR_MOEDA.format(atribuicaoReceita.negocios_ganhos_valor)}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Sinais gerados</div>
              <div className="font-head text-[18px] font-extrabold text-text">{atribuicaoReceita.sinais_gerados}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Sinais convertidos</div>
              <div className="font-head text-[18px] font-extrabold text-text">
                {atribuicaoReceita.sinais_convertidos}
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-muted">Taxa de conversão</div>
              <div className="font-head text-[18px] font-extrabold text-cyan">
                {Math.round(atribuicaoReceita.taxa_conversao_sinais * 100)}%
              </div>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <SectionLabel>Sugestões de Expansão</SectionLabel>
        <p className="mb-3 text-[12px] text-muted">
          Revenue Agent: contas com pelo menos um negócio ganho que ainda não têm nenhum negócio vinculado a uma
          oferta ativa — cross-sell/upsell real, a partir da oferta de cada negócio.
        </p>
        <div className="flex flex-col gap-2">
          {sugestoesExpansao.map((sugestao) => (
            <div
              key={`${sugestao.conta_id}-${sugestao.oferta_id}`}
              className="flex items-center justify-between rounded-lg border border-border p-3 text-[12px]"
            >
              <div>
                <span className="font-semibold text-text">{sugestao.conta_nome}</span>
                <span className="text-muted"> · {sugestao.motivo}</span>
              </div>
              <Badge tone="amber">{sugestao.oferta_nome}</Badge>
            </div>
          ))}
          {sugestoesExpansao.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma sugestão de expansão identificada.</div>
          )}
        </div>
      </Card>

      <TutorialInteligenciaRede open={tutorialAberto} onClose={fecharTutorial} />
    </div>
  );
}
