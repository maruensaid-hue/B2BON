import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";

interface RegraAprendida {
  id: number;
  icp_id: number | null;
  oferta_id: number | null;
  canal: string | null;
  regra: string;
  ativa: boolean;
  criado_em: string;
}

interface IcpResumo {
  id: number;
  nome: string;
}

interface OfertaResumo {
  id: number;
  nome: string;
}

interface CorrecaoRecente {
  id: number;
  tipo: "edicao" | "rejeicao";
  conta_nome: string | null;
  canal: string | null;
  icp_id: number | null;
  oferta_id: number | null;
  conteudo_anterior: string | null;
  conteudo_novo: string | null;
  motivo: string | null;
  criado_em: string;
}

interface EscopoInicial {
  icp_id: number | null;
  oferta_id: number | null;
  canal: string | null;
  regraSugerida?: string;
}

const ROTULOS_CANAL: Record<string, string> = { email: "E-mail", whatsapp: "WhatsApp", linkedin: "LinkedIn" };

function FormularioRegra({
  regra,
  escopoInicial,
  icps,
  ofertas,
  onSalvar,
  salvando,
}: {
  regra: RegraAprendida | null;
  escopoInicial?: EscopoInicial | null;
  icps: IcpResumo[];
  ofertas: OfertaResumo[];
  onSalvar: (event: FormEvent<HTMLFormElement>) => void;
  salvando: boolean;
}) {
  const icpPadrao = regra?.icp_id ?? escopoInicial?.icp_id ?? "";
  const ofertaPadrao = regra?.oferta_id ?? escopoInicial?.oferta_id ?? "";
  const canalPadrao = regra?.canal ?? escopoInicial?.canal ?? "";
  return (
    <form onSubmit={onSalvar} className="flex flex-col gap-3">
      <div>
        <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Regra</div>
        <Textarea
          name="regra"
          required
          rows={3}
          defaultValue={regra?.regra ?? escopoInicial?.regraSugerida}
          placeholder="Ex.: Nunca usar a palavra 'sinergia' — o cliente já reclamou disso em 3 edições diferentes."
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ICP</div>
          <Select name="icp_id" defaultValue={icpPadrao}>
            <option value="">Todos</option>
            {icps.map((icp) => (
              <option key={icp.id} value={icp.id}>
                {icp.nome}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Oferta</div>
          <Select name="oferta_id" defaultValue={ofertaPadrao}>
            <option value="">Todas</option>
            {ofertas.map((oferta) => (
              <option key={oferta.id} value={oferta.id}>
                {oferta.nome}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Canal</div>
          <Select name="canal" defaultValue={canalPadrao}>
            <option value="">Todos</option>
            <option value="email">E-mail</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="linkedin">LinkedIn</option>
          </Select>
        </div>
      </div>
      <div className="text-[11px] text-muted">
        Deixe "Todos"/"Todas" pra aplicar em qualquer geração deste tenant, ou escolha um escopo específico pra
        valer só ali.
      </div>
      <Button type="submit" disabled={salvando} className="mt-1 w-full justify-center">
        {salvando ? "Salvando..." : regra ? "Salvar alterações" : "Criar regra"}
      </Button>
    </form>
  );
}

export function RegrasAprendidas() {
  const [regras, setRegras] = useState<RegraAprendida[]>([]);
  const [correcoes, setCorrecoes] = useState<CorrecaoRecente[]>([]);
  const [icps, setIcps] = useState<IcpResumo[]>([]);
  const [ofertas, setOfertas] = useState<OfertaResumo[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const [regraEmEdicao, setRegraEmEdicao] = useState<RegraAprendida | null>(null);
  const [escopoInicial, setEscopoInicial] = useState<EscopoInicial | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [processandoId, setProcessandoId] = useState<number | null>(null);
  const [confirmandoExcluirId, setConfirmandoExcluirId] = useState<number | null>(null);
  const [sugerindoId, setSugerindoId] = useState<number | null>(null);

  async function carregar() {
    try {
      const [listaRegras, listaCorrecoes, listaIcps, listaOfertas] = await Promise.all([
        api.get<RegraAprendida[]>("/regras-aprendidas"),
        api.get<CorrecaoRecente[]>("/regras-aprendidas/correcoes-recentes"),
        api.get<IcpResumo[]>("/icp"),
        api.get<OfertaResumo[]>("/ofertas"),
      ]);
      setRegras(listaRegras);
      setCorrecoes(listaCorrecoes);
      setIcps(listaIcps);
      setOfertas(listaOfertas);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as regras aprendidas.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  function abrirCriacao() {
    setRegraEmEdicao(null);
    setEscopoInicial(null);
    setModalAberto(true);
  }

  function abrirEdicao(regra: RegraAprendida) {
    setRegraEmEdicao(regra);
    setEscopoInicial(null);
    setModalAberto(true);
  }

  function criarRegraAPartirDaCorrecao(correcao: CorrecaoRecente) {
    setRegraEmEdicao(null);
    setEscopoInicial({ icp_id: correcao.icp_id, oferta_id: correcao.oferta_id, canal: correcao.canal });
    setModalAberto(true);
  }

  async function sugerirComIa(correcao: CorrecaoRecente) {
    if (sugerindoId !== null) return;
    setSugerindoId(correcao.id);
    setErro(null);
    try {
      const { regra_sugerida } = await api.post<{ regra_sugerida: string }>(
        `/regras-aprendidas/correcoes-recentes/${correcao.id}/sugerir-regra`,
      );
      setRegraEmEdicao(null);
      setEscopoInicial({
        icp_id: correcao.icp_id, oferta_id: correcao.oferta_id, canal: correcao.canal,
        regraSugerida: regra_sugerida,
      });
      setModalAberto(true);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível sugerir uma regra com IA.");
    } finally {
      setSugerindoId(null);
    }
  }

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (salvando) return;
    const form = new FormData(event.currentTarget);
    const dados = {
      regra: String(form.get("regra")),
      icp_id: form.get("icp_id") ? Number(form.get("icp_id")) : null,
      oferta_id: form.get("oferta_id") ? Number(form.get("oferta_id")) : null,
      canal: form.get("canal") ? String(form.get("canal")) : null,
    };
    setSalvando(true);
    setErro(null);
    try {
      if (regraEmEdicao) {
        await api.put(`/regras-aprendidas/${regraEmEdicao.id}`, dados);
      } else {
        await api.post("/regras-aprendidas", dados);
      }
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a regra.");
    } finally {
      setSalvando(false);
    }
  }

  async function alternarAtiva(regra: RegraAprendida) {
    setProcessandoId(regra.id);
    setErro(null);
    try {
      await api.post(`/regras-aprendidas/${regra.id}/${regra.ativa ? "desativar" : "ativar"}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível atualizar a regra.");
    } finally {
      setProcessandoId(null);
    }
  }

  async function excluir(regraId: number) {
    setProcessandoId(regraId);
    setErro(null);
    try {
      await api.delete(`/regras-aprendidas/${regraId}`);
      setConfirmandoExcluirId(null);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a regra.");
    } finally {
      setProcessandoId(null);
    }
  }

  function nomeIcp(icpId: number | null): string {
    if (icpId === null) return "Todos";
    return icps.find((icp) => icp.id === icpId)?.nome ?? `#${icpId}`;
  }

  function nomeOferta(ofertaId: number | null): string {
    if (ofertaId === null) return "Todas";
    return ofertas.find((oferta) => oferta.id === ofertaId)?.nome ?? `#${ofertaId}`;
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Regras Aprendidas</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Padrões observados em edições e rejeições de mensagens — escritos por você, aplicados automaticamente
            na próxima geração de cadência
          </div>
        </div>
        <Button size="sm" variant="violet" onClick={abrirCriacao}>
          + Nova regra
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Regras</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Toda regra ativa entra automaticamente no prompt de geração de toques de cadência cujo ICP/Oferta/canal
          batam com o escopo escolhido — "Todos"/"Todas" aplica sempre.
        </div>
        <div className="flex flex-col gap-2">
          {regras.map((regra) => (
            <div
              key={regra.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]"
            >
              <div>
                <div className="flex items-center gap-2">
                  <Badge tone={regra.ativa ? "green" : "muted"}>{regra.ativa ? "Ativa" : "Desativada"}</Badge>
                  <span className="font-semibold text-text">{regra.regra}</span>
                </div>
                <div className="text-muted">
                  ICP: {nomeIcp(regra.icp_id)} · Oferta: {nomeOferta(regra.oferta_id)} · Canal:{" "}
                  {regra.canal ? ROTULOS_CANAL[regra.canal] ?? regra.canal : "Todos"}
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => abrirEdicao(regra)}>
                  Editar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={processandoId === regra.id}
                  onClick={() => alternarAtiva(regra)}
                >
                  {regra.ativa ? "Desativar" : "Ativar"}
                </Button>
                {confirmandoExcluirId === regra.id ? (
                  <Button size="sm" variant="danger" disabled={processandoId === regra.id} onClick={() => excluir(regra.id)}>
                    {processandoId === regra.id ? "Excluindo..." : "Confirmar exclusão?"}
                  </Button>
                ) : (
                  <Button size="sm" variant="danger" onClick={() => setConfirmandoExcluirId(regra.id)}>
                    Excluir
                  </Button>
                )}
              </div>
            </div>
          ))}
          {regras.length === 0 && <div className="text-[12px] text-muted">Nenhuma regra aprendida cadastrada ainda.</div>}
        </div>
      </Card>

      <Card className="mt-4">
        <SectionLabel>Correções recentes</SectionLabel>
        <div className="mb-3 text-[11px] text-muted">
          Edições e rejeições de mensagens geradas pela IA — se notar um padrão se repetindo, crie uma regra a
          partir dele.
        </div>
        <div className="flex flex-col gap-2">
          {correcoes.map((correcao) => (
            <div key={correcao.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5 text-[12px]">
              <div>
                <div className="flex items-center gap-2">
                  <Badge tone={correcao.tipo === "edicao" ? "amber" : "red"}>
                    {correcao.tipo === "edicao" ? "Edição" : "Rejeição"}
                  </Badge>
                  <span className="text-muted">
                    {correcao.conta_nome ?? "Conta sem nome"} ·{" "}
                    {correcao.canal ? ROTULOS_CANAL[correcao.canal] ?? correcao.canal : "—"} ·{" "}
                    {new Date(correcao.criado_em).toLocaleString("pt-BR")}
                  </span>
                </div>
                {correcao.tipo === "edicao" ? (
                  <div className="mt-1 text-text">
                    <span className="text-muted line-through">{correcao.conteudo_anterior}</span>
                    <span className="mx-1 text-muted">→</span>
                    <span>{correcao.conteudo_novo}</span>
                  </div>
                ) : (
                  <div className="mt-1 text-text">Motivo: {correcao.motivo ?? "não informado"}</div>
                )}
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={sugerindoId === correcao.id}
                  onClick={() => sugerirComIa(correcao)}
                >
                  {sugerindoId === correcao.id ? "Sugerindo..." : "✨ Sugerir com IA"}
                </Button>
                <Button size="sm" variant="violet" onClick={() => criarRegraAPartirDaCorrecao(correcao)}>
                  Criar regra a partir disso
                </Button>
              </div>
            </div>
          ))}
          {correcoes.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma edição ou rejeição registrada ainda.</div>
          )}
        </div>
      </Card>

      <Modal
        title={regraEmEdicao ? "Editar regra aprendida" : "Nova regra aprendida"}
        open={modalAberto}
        onClose={() => setModalAberto(false)}
      >
        <FormularioRegra
          key={regraEmEdicao?.id ?? JSON.stringify(escopoInicial) ?? "novo"}
          regra={regraEmEdicao}
          escopoInicial={escopoInicial}
          icps={icps}
          ofertas={ofertas}
          onSalvar={salvar}
          salvando={salvando}
        />
      </Modal>
    </div>
  );
}
