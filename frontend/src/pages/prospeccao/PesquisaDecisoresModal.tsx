import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, mensagemErro } from "@/lib/api";

interface Bloqueio {
  codigo: string;
  mensagem: string;
}

interface Ajuste {
  tipo: "reduzir_profundidade" | "ampliar_abrangencia" | "reduzir_selecao";
  decisores_por_empresa: number;
  empresas_cobertas: number;
}

interface CategoriaFonte {
  creditos_provedor_max?: number;
  creditos_cliente_max: number;
  observacao?: string;
}

interface Estimativa {
  creditos_maximos: number;
  creditos_provedor_maximos: number;
  valor_maximo_brl: string;
  preco_credito_provedor_brl: string;
  decisores_solicitados: number;
  dados_a_revelar: { emails: boolean; telefones: boolean; rotulo: string; creditos_por_decisor: number };
  por_categoria: {
    ia: { creditos: number; observacao: string };
    enriquecimento: { lusha_busca: CategoriaFonte; lusha_revelacao: CategoriaFonte; receita_qsa: CategoriaFonte; brasilapi: CategoriaFonte };
  };
  empresas_selecionadas: number;
  empresas_a_consultar: number;
  empresas_deduplicadas: number;
  decisores_por_empresa: number;
  origem_decisores: "padrao_plano" | "informado_usuario";
  disponivel: number;
  limite_periodo_restante: number | null;
  limites: {
    decisores_por_empresa_max: number;
    itens_por_lote_max: number | null;
    limite_periodo_creditos: number | null;
    limite_creditos_pesquisa: number | null;
    limite_pesquisas_periodo: number | null;
    limite_empresas_periodo: number | null;
    limite_contatos_periodo: number | null;
  };
  uso_no_periodo: { pesquisas: number; empresas: number; contatos: number };
  viavel: boolean;
  bloqueios: Bloqueio[];
  ajustes_sugeridos: Ajuste[];
  nota_ajustes: string;
  incertezas: string[];
}

interface ItemPesquisa {
  id: number;
  conta_id: number;
  conta_nome: string | null;
  estado: string;
  motivo: string | null;
  decisores_solicitados: number;
  decisores_retornados: number;
  decisores_com_linkedin: number | null;
  creditos_reservados: number;
  creditos_consumidos: number;
  provedor_medidos: number | null;
}

interface Pesquisa {
  id: string;
  estado: string;
  selecao_hash: string;
  decisores_por_empresa: number;
  total_maximo: number;
  creditos_reservados: number;
  creditos_consumidos: number;
  provedor_reservados: number;
  provedor_consumidos: number;
  requer_reconciliacao: boolean;
  estimativa: Estimativa;
  itens?: ItemPesquisa[];
}

interface PainelResumo {
  plano: {
    disponivel: boolean;
    modo?: string;
    decisores_por_empresa_padrao?: number | null;
    decisores_por_empresa_max?: number | null;
    limite_creditos_pesquisa?: number | null;
    orientacao?: string | null;
  };
  lusha: { disponivel: boolean; motivos: { codigo: string; mensagem: string }[] };
  composicao?: { franquia_restante: number; adicional_restante: number; expira_em: string };
  dados_a_revelar?: {
    emails: { disponivel: boolean; creditos_por_decisor: number };
    telefones: { disponivel: boolean; creditos_por_decisor: number };
    linkedin: string;
  } | null;
}

const ROTULO_AJUSTE: Record<Ajuste["tipo"], string> = {
  reduzir_profundidade: "Menos decisores por empresa, mesmas empresas",
  ampliar_abrangencia: "Mais empresas com 1 decisor cada",
  reduzir_selecao: "Mesmos decisores por empresa, menos empresas",
};

const ROTULO_ESTADO: Record<string, string> = {
  criada: "Aguardando confirmação",
  reservada: "Créditos reservados — consultando o provedor",
  enviada: "Em andamento",
  em_processamento: "Aguardando reconciliação do administrador",
  concluida: "Concluída",
  parcial: "Concluída com falhas em algumas empresas",
  falha: "Falhou (nenhum crédito consumido)",
  cancelada: "Cancelada",
  reconciliada: "Concluída e reconciliada",
};

const TOM_ITEM: Record<string, "green" | "amber" | "red" | "muted" | "cyan"> = {
  concluido: "green", sem_resultados: "muted", deduplicada: "muted", falha: "red", ambiguo: "amber", pendente: "cyan", enviado: "cyan", cancelado: "muted",
};

interface Props {
  contaIds: number[];
  onClose: () => void;
  onConcluida?: () => void;
}

/** Pesquisa de decisores em provedor pago: o usuário escolhe quantos por empresa, REVÊ a estimativa e só então confirma. Nada é reservado nem
 * consultado antes da confirmação, e o servidor revalida tudo (saldo, limites, orçamento) no clique em "Confirmar". */
export function PesquisaDecisoresModal({ contaIds, onClose, onConcluida }: Props) {
  const [painel, setPainel] = useState<PainelResumo | null>(null);
  const [valor, setValor] = useState("");
  // Dados a revelar em CADA pesquisa (escolha do usuário, conforme os créditos que tem): e-mail marcado por padrão. O link do LinkedIn acompanha sempre.
  const [revelarEmails, setRevelarEmails] = useState(true);
  const [revelarTelefones, setRevelarTelefones] = useState(false);
  const [pesquisa, setPesquisa] = useState<Pesquisa | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Uma chave por prévia: clicar duas vezes em "Confirmar" (ou repetir após timeout) reaproveita a mesma chave e nunca reserva em dobro.
  const chave = useRef<string | null>(null);
  const montado = useRef(true);

  useEffect(() => {
    montado.current = true;
    api
      .get<PainelResumo>("/pesquisas-decisores/painel")
      .then((p) => {
        setPainel(p);
        // Plano com teto de 1 decisor (ex.: POC): o único valor possível já vem escolhido.
        if (p.plano.decisores_por_empresa_max === 1) setValor("1");
      })
      .catch(() => setPainel(null));
    return () => {
      montado.current = false;
    };
  }, []);

  // A consulta ao provedor roda em segundo plano no servidor; aqui só se acompanha o andamento até a pesquisa sair de "reservada/enviada".
  const acompanhar = useCallback(async (id: string) => {
    for (let tentativa = 0; tentativa < 150 && montado.current; tentativa++) {
      await new Promise((r) => setTimeout(r, 2000));
      if (!montado.current) return;
      try {
        const atual = await api.get<Pesquisa>(`/pesquisas-decisores/${id}`);
        setPesquisa(atual);
        if (atual.estado !== "reservada" && atual.estado !== "enviada") return;
      } catch {
        /* servidor ocupado: tenta de novo no próximo ciclo */
      }
    }
  }, []);

  const plano = painel?.plano;
  const lusha = painel?.lusha;
  const liberado = lusha === undefined ? plano?.disponivel !== false : lusha.disponivel;
  // Sem padrão no plano, o número de decisores é escolha obrigatória do usuário (nunca é assumido em silêncio).
  const semPadrao = plano !== undefined && !plano.decisores_por_empresa_padrao;
  const dadosPainel = painel?.dados_a_revelar ?? null;
  const telefoneIndisponivel = dadosPainel !== null && !dadosPainel.telefones.disponivel;
  const nenhumDado = !revelarEmails && !revelarTelefones;
  const porDecisor = (revelarEmails ? (dadosPainel?.emails.creditos_por_decisor ?? 0) : 0) + (revelarTelefones ? (dadosPainel?.telefones.creditos_por_decisor ?? 0) : 0);
  const opcoes = Array.from({ length: Math.min(plano?.decisores_por_empresa_max ?? 10, 50) }, (_, i) => i + 1);

  async function revisar() {
    setCarregando(true);
    setErro(null);
    try {
      const corpo: { conta_ids: number[]; decisores_por_empresa?: number; revelar_emails: boolean; revelar_telefones: boolean } = {
        conta_ids: contaIds,
        revelar_emails: revelarEmails,
        revelar_telefones: revelarTelefones,
      };
      if (valor.trim() !== "") corpo.decisores_por_empresa = Number(valor);
      const criada = await api.post<Pesquisa>("/pesquisas-decisores/previa", corpo);
      chave.current = crypto.randomUUID();
      setPesquisa(criada);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível montar a estimativa."));
    } finally {
      setCarregando(false);
    }
  }

  async function confirmar() {
    if (!pesquisa || !chave.current) return;
    setCarregando(true);
    setErro(null);
    try {
      const resultado = await api.post<Pesquisa>(`/pesquisas-decisores/${pesquisa.id}/confirmar`, {
        selecao_hash: pesquisa.selecao_hash,
        idempotency_key: chave.current,
      });
      setPesquisa(resultado);
      if (resultado.estado === "reservada" || resultado.estado === "enviada") await acompanhar(resultado.id);
      onConcluida?.();
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível confirmar a pesquisa."));
    } finally {
      setCarregando(false);
    }
  }

  async function retomar() {
    if (!pesquisa) return;
    setCarregando(true);
    setErro(null);
    try {
      const retomada = await api.post<Pesquisa>(`/pesquisas-decisores/${pesquisa.id}/retomar`, {});
      setPesquisa(retomada);
      if (retomada.estado === "reservada" || retomada.estado === "enviada") await acompanhar(retomada.id);
      onConcluida?.();
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível retomar a pesquisa."));
    } finally {
      setCarregando(false);
    }
  }

  async function cancelar() {
    if (!pesquisa) return onClose();
    setCarregando(true);
    try {
      await api.post(`/pesquisas-decisores/${pesquisa.id}/cancelar`, {});
    } catch {
      /* a prévia expira sozinha */
    } finally {
      setCarregando(false);
      onClose();
    }
  }

  function aplicarSugestao(ajuste: Ajuste) {
    // Só preenche o campo: a escolha do usuário nunca muda sozinha, e a nova estimativa precisa ser revista de novo.
    setValor(String(ajuste.decisores_por_empresa));
    setPesquisa(null);
    chave.current = null;
  }

  const e = pesquisa?.estimativa;
  const emRevisao = pesquisa?.estado === "criada";
  const terminou = pesquisa !== null && !emRevisao;

  return (
    <Modal title="Pesquisar decisores" open onClose={onClose}>
      <div className="space-y-3 text-[12px]">
        {!pesquisa && (
          <>
            <p className="text-muted">
              {contaIds.length} empresa(s) escolhida(s). A busca e a revelação de contatos têm tarifas próprias no provedor, e o que se cobra é o consumo que o próprio
              provedor informa, em créditos de enriquecimento (separados dos créditos de IA). Nada é consultado antes de você revisar e confirmar.
            </p>
            {!liberado && (
              <div className="rounded-md bg-surf2 p-2 text-amber">
                <p className="mb-1 font-semibold">A pesquisa de decisores (Lusha) está indisponível agora.</p>
                <ul className="list-disc space-y-0.5 pl-4">
                  {(lusha?.motivos ?? []).map((m) => (
                    <li key={m.codigo}>{m.mensagem}</li>
                  ))}
                  {!lusha && <li>{plano?.orientacao ?? "A pesquisa de decisores não está liberada no seu plano."}</li>}
                </ul>
                <p className="mt-1 text-[10.5px] text-muted">O mapeamento de decisores pelo QSA da Receita continua funcionando normalmente.</p>
              </div>
            )}
            <div>
              <label className="mb-1 block text-[10px] tracking-wide text-muted uppercase" htmlFor="decisores-por-empresa">
                Decisores por empresa
              </label>
              <Select id="decisores-por-empresa" value={valor} onChange={(ev) => setValor(ev.target.value)}>
                <option value="">{semPadrao ? "Escolha quantos decisores por empresa..." : `Padrão do plano (${plano?.decisores_por_empresa_padrao})`}</option>
                {opcoes.map((n) => (
                  <option key={n} value={String(n)}>
                    {n} {n === 1 ? "decisor" : "decisores"} por empresa
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-[10.5px] text-muted">
                {plano?.decisores_por_empresa_max ? `Máximo no seu plano: ${plano.decisores_por_empresa_max} por empresa, em cada pesquisa. ` : ""}
                {plano?.limite_creditos_pesquisa ? `Limite desta pesquisa: ${plano.limite_creditos_pesquisa} crédito(s). ` : ""}
                Mais decisores por empresa gasta mais créditos e cobre menos empresas; a escolha nunca é alterada sem a sua confirmação.
              </p>
              {plano?.modo === "poc_autorizada" && <p className="mt-1 text-[10.5px] text-muted">POC: 1 decisor por empresa, dentro do orçamento autorizado para a sua operação.</p>}
            </div>
            <fieldset className="rounded-md bg-surf2 p-2">
              <legend className="px-1 text-[10px] tracking-wide text-muted uppercase">Dados a revelar de cada decisor</legend>
              <label className="flex cursor-pointer items-start gap-2 py-0.5">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={revelarEmails}
                  onChange={(ev) => setRevelarEmails(ev.target.checked)}
                />
                <span>
                  <span className="font-semibold">E-mail</span>
                  {dadosPainel && <span className="text-muted"> · {dadosPainel.emails.creditos_por_decisor} crédito(s) por decisor</span>}
                </span>
              </label>
              <label className={`flex items-start gap-2 py-0.5 ${telefoneIndisponivel ? "opacity-60" : "cursor-pointer"}`}>
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={revelarTelefones && !telefoneIndisponivel}
                  disabled={telefoneIndisponivel}
                  onChange={(ev) => setRevelarTelefones(ev.target.checked)}
                />
                <span>
                  <span className="font-semibold">Telefone</span>
                  {dadosPainel && !telefoneIndisponivel && <span className="text-muted"> · {dadosPainel.telefones.creditos_por_decisor} crédito(s) por decisor</span>}
                  {telefoneIndisponivel && <span className="text-muted"> · indisponível: o provedor não informou a tarifa</span>}
                </span>
              </label>
              <p className="mt-1 text-[10.5px] text-muted">
                O link do perfil no LinkedIn vem junto com todo decisor encontrado, sem crédito extra, sempre que o provedor o informa.
                {dadosPainel && porDecisor > 0 ? ` Com esta escolha, cada decisor custa até ${porDecisor} crédito(s), além da busca da empresa.` : ""} Escolha conforme os créditos que
                você tem: dá para gastar toda a franquia em uma única empresa ou pesquisar o máximo de decisores só com o e-mail.
              </p>
              {nenhumDado && <p className="mt-1 text-red">Marque ao menos um dado: e-mail ou telefone.</p>}
            </fieldset>
            {erro && <p className="text-red">{erro}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onClose}>
                Fechar
              </Button>
              <Button size="sm" disabled={carregando || !liberado || nenhumDado || (semPadrao && valor === "")} onClick={revisar}>
                {carregando ? "Calculando..." : "Revisar estimativa"}
              </Button>
            </div>
          </>
        )}

        {pesquisa && e && emRevisao && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Resumo rotulo="Empresas a consultar" valor={`${e.empresas_a_consultar} de ${e.empresas_selecionadas}`} />
              <Resumo
                rotulo="Decisores por empresa"
                valor={`${e.decisores_por_empresa} (${e.origem_decisores === "padrao_plano" ? "padrão do plano" : "escolha sua"})`}
              />
              <Resumo rotulo="Créditos de enriquecimento (teto)" valor={String(e.creditos_maximos)} destaque />
              <Resumo rotulo="Saldo disponível" valor={String(e.disponivel)} />
              {e.limites.limite_creditos_pesquisa !== null && <Resumo rotulo="Limite por pesquisa" valor={`${e.limites.limite_creditos_pesquisa} crédito(s)`} />}
              <Resumo rotulo="Máx. de decisores por empresa" valor={String(e.limites.decisores_por_empresa_max)} />
              <Resumo rotulo="Valor máximo estimado" valor={`R$ ${e.valor_maximo_brl.replace(".", ",")}`} />
              <Resumo rotulo="Decisores pedidos" valor={String(e.decisores_solicitados)} />
              <Resumo rotulo="Dados a revelar" valor={`${e.dados_a_revelar.rotulo} + LinkedIn`} />
            </div>
            <div className="rounded-md bg-surf2 p-2 text-[11px] text-muted">
              <p className="mb-0.5 font-semibold text-text">Teto por categoria (créditos do provedor)</p>
              <p>Busca: até {e.por_categoria.enriquecimento.lusha_busca.creditos_provedor_max} · Revelação de contatos: até {e.por_categoria.enriquecimento.lusha_revelacao.creditos_provedor_max}</p>
              <p>IA: {e.por_categoria.ia.creditos} (esta operação não usa IA) · QSA da Receita e Brasil API: sem consumo de crédito</p>
              <p>Preço por crédito do provedor ≈ R$ {e.preco_credito_provedor_brl.replace(".", ",")} (valor de apresentação). O que se cobra é o consumo medido pelo provedor, que pode ser menor.</p>
            </div>
            {(e.limites.limite_pesquisas_periodo !== null || e.limites.limite_empresas_periodo !== null || e.limites.limite_contatos_periodo !== null) && (
              <p className="text-[11px] text-muted">
                Uso no mês: {e.uso_no_periodo.pesquisas} pesquisa(s){e.limites.limite_pesquisas_periodo !== null ? ` de ${e.limites.limite_pesquisas_periodo}` : ""} ·{" "}
                {e.uso_no_periodo.empresas} empresa(s){e.limites.limite_empresas_periodo !== null ? ` de ${e.limites.limite_empresas_periodo}` : ""} ·{" "}
                {e.uso_no_periodo.contatos} contato(s){e.limites.limite_contatos_periodo !== null ? ` de ${e.limites.limite_contatos_periodo}` : ""}
              </p>
            )}
            {e.empresas_deduplicadas > 0 && <p className="text-muted">{e.empresas_deduplicadas} empresa(s) ficam fora da consulta (duplicadas ou decisores já obtidos).</p>}
            {e.bloqueios.length > 0 && (
              <div className="rounded-md bg-surf2 p-2">
                <p className="mb-1 font-semibold text-red">Não é possível confirmar agora</p>
                <ul className="list-disc space-y-0.5 pl-4">
                  {e.bloqueios.map((b) => (
                    <li key={b.codigo}>{b.mensagem}</li>
                  ))}
                </ul>
                {e.bloqueios.some((b) => b.codigo === "saldo_insuficiente") && !e.bloqueios.some((b) => b.codigo === "limite_por_pesquisa") && (
                  <p className="mt-1 text-[11px] text-muted">
                    Faltou saldo: veja os <a className="text-cyan underline" href="/creditos-enriquecimento">pacotes de créditos adicionais</a> (valem até o fim do mês e não aumentam o limite por pesquisa).
                  </p>
                )}
              </div>
            )}
            {e.ajustes_sugeridos.length > 0 && (
              <div className="rounded-md bg-surf2 p-2">
                <p className="mb-1 font-semibold">Alternativas (você decide)</p>
                <ul className="space-y-1">
                  {e.ajustes_sugeridos.map((a) => (
                    <li key={a.tipo} className="flex items-center justify-between gap-2">
                      <span>
                        {ROTULO_AJUSTE[a.tipo]}: {a.decisores_por_empresa} por empresa, até {a.empresas_cobertas} empresa(s)
                      </span>
                      {a.tipo !== "reduzir_selecao" && (
                        <Button size="sm" variant="ghost" onClick={() => aplicarSugestao(a)}>
                          Usar {a.decisores_por_empresa}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-[10.5px] text-muted">{e.nota_ajustes}</p>
              </div>
            )}
            <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-muted">
              {e.incertezas.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
            {erro && <p className="text-red">{erro}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" disabled={carregando} onClick={cancelar}>
                Cancelar
              </Button>
              <Button variant="ghost" size="sm" disabled={carregando} onClick={() => setPesquisa(null)}>
                Voltar
              </Button>
              <Button size="sm" disabled={carregando || !e.viavel} onClick={confirmar}>
                {carregando ? "Pesquisando..." : `Confirmar (teto de ${e.creditos_maximos} crédito(s))`}
              </Button>
            </div>
          </>
        )}

        {terminou && pesquisa && (
          <>
            <div className="flex items-center gap-2">
              <Badge tone={pesquisa.estado === "concluida" || pesquisa.estado === "reconciliada" ? "green" : pesquisa.estado === "falha" ? "red" : "amber"}>
                {ROTULO_ESTADO[pesquisa.estado] ?? pesquisa.estado}
              </Badge>
              <span className="text-muted">
                {pesquisa.creditos_consumidos} crédito(s) de enriquecimento consumido(s) (medido pelo provedor: {pesquisa.provedor_consumidos}) de {pesquisa.creditos_reservados} reservado(s)
              </span>
            </div>
            {pesquisa.requer_reconciliacao && (
              <p className="rounded-md bg-surf2 p-2 text-amber">
                Alguma empresa teve resultado incerto no provedor. Os créditos dela ficam retidos até um administrador conferir o uso informado pelo provedor. Nada é
                repetido automaticamente.
              </p>
            )}
            <table className="w-full border-collapse">
              <tbody>
                {(pesquisa.itens ?? []).map((i) => (
                  <tr key={i.id} className="border-b border-border">
                    <td className="p-1.5 font-semibold">{i.conta_nome ?? `#${i.conta_id}`}</td>
                    <td className="p-1.5">
                      <Badge tone={TOM_ITEM[i.estado] ?? "muted"}>{i.estado}</Badge>
                    </td>
                    <td className="p-1.5 text-right text-muted">
                      {i.decisores_retornados} decisor(es)
                      {i.decisores_com_linkedin !== null && i.decisores_retornados > 0 ? ` · ${i.decisores_com_linkedin} com LinkedIn` : ""}
                      {i.provedor_medidos !== null ? ` · ${i.provedor_medidos} crédito(s) do provedor` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {erro && <p className="text-red">{erro}</p>}
            <div className="flex justify-end gap-2">
              {(pesquisa.estado === "enviada" || pesquisa.estado === "reservada") && (
                <Button size="sm" disabled={carregando} onClick={retomar}>
                  {carregando ? "Consultando..." : "Continuar as empresas pendentes"}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={onClose}>
                Fechar
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

function Resumo({ rotulo, valor, destaque }: { rotulo: string; valor: string; destaque?: boolean }) {
  return (
    <div className="rounded-md bg-surf2 p-2">
      <div className="text-[9.5px] tracking-wide text-muted uppercase">{rotulo}</div>
      <div className={destaque ? "text-[15px] font-bold text-cyan" : "font-semibold"}>{valor}</div>
    </div>
  );
}
