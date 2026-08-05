import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { Conta, ICP } from "@/pages/prospeccao/Prospeccao";
import { api, ApiError } from "@/lib/api";

interface Cadencia {
  id: number;
  nome: string;
  canais: string[];
  status: "rascunho" | "aguardando_aprovacao" | "ativa";
  tipo: string;
  data_inicio: string | null;
}

interface ToqueCadencia {
  id: number;
  ordem: number;
  canal: string;
  intervalo_dias_apos_anterior: number;
  template_whatsapp_id: string | null;
  ab_teste_habilitado: boolean;
}

interface ToqueRascunho {
  ordem: number;
  canal: string;
  intervalo_dias_apos_anterior: number;
  template_whatsapp_id: string;
  ab_teste_habilitado: boolean;
}

interface GerarLoteResultado {
  contas_processadas: number[];
  contas_sem_decisor: number[];
  mensagens_geradas: number;
}

function toqueVazio(ordem: number, canal: string): ToqueRascunho {
  return { ordem, canal, intervalo_dias_apos_anterior: ordem === 1 ? 0 : 2, template_whatsapp_id: "", ab_teste_habilitado: false };
}

function toneStatus(status: string): "cyan" | "amber" | "green" {
  if (status === "ativa") return "green";
  if (status === "aguardando_aprovacao") return "amber";
  return "cyan";
}

export function Cadencias() {
  const [cadencias, setCadencias] = useState<Cadencia[]>([]);
  const [cadenciaSelecionadaId, setCadenciaSelecionadaId] = useState<number | null>(null);
  const [toques, setToques] = useState<ToqueCadencia[]>([]);
  const [icps, setIcps] = useState<ICP[]>([]);
  const [icpParaLoteId, setIcpParaLoteId] = useState<number | null>(null);
  const [contasDoIcp, setContasDoIcp] = useState<Conta[]>([]);
  const [contasSelecionadas, setContasSelecionadas] = useState<Set<number>>(new Set());
  const [modalCriarAberto, setModalCriarAberto] = useState(false);
  const [rascunhoToques, setRascunhoToques] = useState<ToqueRascunho[]>([
    toqueVazio(1, "email"),
    toqueVazio(2, "whatsapp"),
    toqueVazio(3, "email"),
    toqueVazio(4, "linkedin"),
    toqueVazio(5, "whatsapp"),
  ]);
  const [resultadoGeracao, setResultadoGeracao] = useState<GerarLoteResultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const cadenciaSelecionada = cadencias.find((c) => c.id === cadenciaSelecionadaId) ?? null;

  async function carregarCadencias() {
    try {
      const resposta = await api.get<Cadencia[]>("/cadencias");
      setCadencias(resposta);
      if (resposta.length > 0 && cadenciaSelecionadaId === null) {
        setCadenciaSelecionadaId(resposta[0].id);
      }
    } catch {
      setErro("Não foi possível carregar as cadências.");
    }
  }

  async function carregarIcps() {
    try {
      const resposta = await api.get<ICP[]>("/icp");
      setIcps(resposta);
    } catch {
      setErro("Não foi possível carregar os ICPs.");
    }
  }

  useEffect(() => {
    carregarCadencias();
    carregarIcps();
  }, []);

  useEffect(() => {
    if (cadenciaSelecionadaId === null) return;
    setResultadoGeracao(null);
    api
      .get<ToqueCadencia[]>(`/cadencias/${cadenciaSelecionadaId}/toques`)
      .then(setToques)
      .catch(() => setErro("Não foi possível carregar os toques da cadência."));
  }, [cadenciaSelecionadaId]);

  useEffect(() => {
    if (icpParaLoteId === null) {
      setContasDoIcp([]);
      return;
    }
    setContasSelecionadas(new Set());
    api
      .get<Conta[]>(`/icp/${icpParaLoteId}/contas`)
      .then(setContasDoIcp)
      .catch(() => setErro("Não foi possível carregar as contas do ICP."));
  }, [icpParaLoteId]);

  function atualizarToque(indice: number, campo: keyof ToqueRascunho, valor: string | boolean) {
    setRascunhoToques((atual) =>
      atual.map((toque, i) => (i === indice ? { ...toque, [campo]: valor } : toque)),
    );
  }

  function adicionarToque() {
    setRascunhoToques((atual) => [...atual, toqueVazio(atual.length + 1, "email")]);
  }

  function removerToque(indice: number) {
    setRascunhoToques((atual) =>
      atual.filter((_, i) => i !== indice).map((toque, i) => ({ ...toque, ordem: i + 1 })),
    );
  }

  async function criarCadencia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/cadencias", {
        nome: String(form.get("nome")),
        tipo: String(form.get("tipo")),
        toques: rascunhoToques.map((toque) => ({
          ordem: toque.ordem,
          canal: toque.canal,
          intervalo_dias_apos_anterior: Number(toque.intervalo_dias_apos_anterior),
          template_whatsapp_id: toque.canal === "whatsapp" ? toque.template_whatsapp_id || null : null,
          ab_teste_habilitado: toque.ab_teste_habilitado,
        })),
      });
      setModalCriarAberto(false);
      setRascunhoToques([
        toqueVazio(1, "email"),
        toqueVazio(2, "whatsapp"),
        toqueVazio(3, "email"),
        toqueVazio(4, "linkedin"),
        toqueVazio(5, "whatsapp"),
      ]);
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar a cadência.");
    }
  }

  function alternarConta(contaId: number) {
    setContasSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(contaId)) nova.delete(contaId);
      else nova.add(contaId);
      return nova;
    });
  }

  async function gerarParaLote() {
    if (cadenciaSelecionadaId === null || contasSelecionadas.size === 0) return;
    setErro(null);
    try {
      const resultado = await api.post<GerarLoteResultado>(`/cadencias/${cadenciaSelecionadaId}/gerar`, {
        conta_ids: Array.from(contasSelecionadas),
      });
      setResultadoGeracao(resultado);
      setContasSelecionadas(new Set());
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível gerar as mensagens.");
    }
  }

  async function ativarCadencia() {
    if (cadenciaSelecionadaId === null) return;
    setErro(null);
    try {
      await api.post(`/cadencias/${cadenciaSelecionadaId}/ativar`);
      setMensagem("Cadência ativada — os envios entram na fila conforme o agendamento de cada toque.");
      await carregarCadencias();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível ativar a cadência.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Cadências</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Sequência de toques multicanal gerada por IA, mediante aprovação
          </div>
        </div>
        <Button size="sm" variant="violet" onClick={() => setModalCriarAberto(true)}>
          + Nova cadência
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <Card className="mb-4">
        <SectionLabel>Cadências</SectionLabel>
        <div className="flex flex-wrap gap-2">
          {cadencias.map((cadencia) => (
            <button
              key={cadencia.id}
              onClick={() => setCadenciaSelecionadaId(cadencia.id)}
              className={`rounded-lg border px-3 py-1.5 text-[12px] ${
                cadencia.id === cadenciaSelecionadaId
                  ? "border-cyan bg-cyan/15 text-cyan"
                  : "border-border text-muted hover:text-text"
              }`}
            >
              {cadencia.nome}
            </button>
          ))}
          {cadencias.length === 0 && <div className="text-[12px] text-muted">Nenhuma cadência criada ainda.</div>}
        </div>
      </Card>

      {cadenciaSelecionada && (
        <>
          <Card className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <SectionLabel>{cadenciaSelecionada.nome}</SectionLabel>
              <div className="flex items-center gap-2">
                <Badge tone={toneStatus(cadenciaSelecionada.status)}>{cadenciaSelecionada.status}</Badge>
                {cadenciaSelecionada.status === "aguardando_aprovacao" && (
                  <Button size="sm" onClick={ativarCadencia}>
                    Ativar cadência
                  </Button>
                )}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              {toques.map((toque) => (
                <div key={toque.id} className="flex items-center gap-2 text-[12px] text-muted">
                  <span className="font-head font-bold text-text">#{toque.ordem}</span>
                  <Badge tone="cyan">{toque.canal}</Badge>
                  <span>
                    {toque.ordem === 1 ? "imediato" : `${toque.intervalo_dias_apos_anterior}d depois do anterior`}
                  </span>
                  {toque.ab_teste_habilitado && <Badge tone="amber">teste A/B</Badge>}
                </div>
              ))}
            </div>
          </Card>

          {cadenciaSelecionada.status === "rascunho" && (
            <Card>
              <SectionLabel>Selecionar contas para gerar mensagens</SectionLabel>
              <div className="mb-3">
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">ICP</div>
                <Select
                  value={icpParaLoteId ?? ""}
                  onChange={(event) => setIcpParaLoteId(event.target.value ? Number(event.target.value) : null)}
                >
                  <option value="">Selecione um ICP</option>
                  {icps.map((icp) => (
                    <option key={icp.id} value={icp.id}>
                      {icp.nome} {!icp.ativo && "(inativo)"}
                    </option>
                  ))}
                </Select>
              </div>

              {contasDoIcp.length > 0 && (
                <div className="mb-3 flex max-h-64 flex-col gap-1 overflow-y-auto rounded-lg border border-border p-2">
                  {contasDoIcp.map((conta) => (
                    <label key={conta.id} className="flex items-center gap-2 text-[12px]">
                      <input
                        type="checkbox"
                        checked={contasSelecionadas.has(conta.id)}
                        onChange={() => alternarConta(conta.id)}
                      />
                      {conta.nome}
                    </label>
                  ))}
                </div>
              )}
              {icpParaLoteId !== null && contasDoIcp.length === 0 && (
                <div className="mb-3 text-[12px] text-muted">Nenhuma conta gerada para esse ICP ainda.</div>
              )}

              <Button disabled={contasSelecionadas.size === 0} onClick={gerarParaLote}>
                Gerar mensagens para {contasSelecionadas.size} conta(s)
              </Button>

              {resultadoGeracao && (
                <div className="mt-3 text-[12px] text-muted">
                  <div>{resultadoGeracao.mensagens_geradas} mensagem(ns) geradas — revise na fila de Aprovações.</div>
                  {resultadoGeracao.contas_sem_decisor.length > 0 && (
                    <div className="mt-1 text-amber">
                      {resultadoGeracao.contas_sem_decisor.length} conta(s) sem decisor mapeado, ficaram de fora —
                      mapeie um decisor na conta antes de tentar de novo.
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </>
      )}

      <Modal title="Nova cadência" open={modalCriarAberto} onClose={() => setModalCriarAberto(false)}>
        <form onSubmit={criarCadencia} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome</div>
            <Input name="nome" required placeholder="Ex.: Prospecção clínicas — SP/RJ" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
            <Select name="tipo" defaultValue="prospeccao">
              <option value="prospeccao">Prospecção</option>
              <option value="nutricao">Nutrição</option>
            </Select>
          </div>

          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
            Toques (mínimo 5, em pelo menos 2 canais)
          </div>
          <div className="flex flex-col gap-2">
            {rascunhoToques.map((toque, indice) => (
              <div key={indice} className="flex items-center gap-1.5 rounded-lg border border-border p-2">
                <span className="w-5 flex-shrink-0 text-center text-[11px] text-muted">#{toque.ordem}</span>
                <Select
                  className="flex-1"
                  value={toque.canal}
                  onChange={(event) => atualizarToque(indice, "canal", event.target.value)}
                >
                  <option value="email">E-mail</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="linkedin">LinkedIn</option>
                </Select>
                <Input
                  type="number"
                  min={0}
                  className="w-20"
                  value={toque.intervalo_dias_apos_anterior}
                  onChange={(event) => atualizarToque(indice, "intervalo_dias_apos_anterior", event.target.value)}
                  title="Dias após o toque anterior"
                />
                <Button type="button" size="sm" variant="danger" onClick={() => removerToque(indice)}>
                  ✕
                </Button>
              </div>
            ))}
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={adicionarToque}>
            + Adicionar toque
          </Button>

          <Button type="submit" className="mt-1 w-full justify-center">
            Criar cadência
          </Button>
        </form>
      </Modal>
    </div>
  );
}
