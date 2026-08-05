import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface ItemFila {
  aprovacao_id: number;
  status: string;
  mensagem_id: number;
  canal: string;
  template_id: string | null;
  conteudo: string;
  cadencia_id: number | null;
  conta_id: number;
  decisor_id: number;
  criado_em: string;
}

function toneCanal(canal: string): "cyan" | "green" | "violet" {
  if (canal === "whatsapp") return "green";
  if (canal === "linkedin") return "violet";
  return "cyan";
}

export function Aprovacoes() {
  const [itens, setItens] = useState<ItemFila[]>([]);
  const [filtroCanal, setFiltroCanal] = useState("");
  const [textoEditado, setTextoEditado] = useState<Record<number, string>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  async function carregar() {
    try {
      const params = new URLSearchParams({ status: "pendente" });
      if (filtroCanal) params.set("canal", filtroCanal);
      const resposta = await api.get<ItemFila[]>(`/aprovacoes?${params.toString()}`);
      setItens(resposta);
    } catch {
      setErro("Não foi possível carregar a fila de aprovação.");
    }
  }

  useEffect(() => {
    carregar();
  }, [filtroCanal]);

  async function aprovar(aprovacaoId: number) {
    try {
      await api.post(`/aprovacoes/${aprovacaoId}/aprovar`);
      setMensagem("Mensagem aprovada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aprovar.");
    }
  }

  async function rejeitar(aprovacaoId: number) {
    try {
      await api.post(`/aprovacoes/${aprovacaoId}/rejeitar`, {});
      setMensagem("Mensagem rejeitada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível rejeitar.");
    }
  }

  async function salvarEdicao(item: ItemFila) {
    const novoConteudo = textoEditado[item.aprovacao_id];
    if (novoConteudo === undefined || novoConteudo === item.conteudo) return;
    try {
      await api.put(`/aprovacoes/${item.aprovacao_id}/mensagem`, { conteudo: novoConteudo });
      setMensagem("Mensagem editada.");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a edição.");
    }
  }

  async function aprovarTudoVisivel() {
    if (itens.length === 0) return;
    try {
      await api.post("/aprovacoes/aprovar-lote", { ids: itens.map((item) => item.aprovacao_id) });
      setMensagem(`${itens.length} mensagem(ns) aprovadas.`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível aprovar em lote.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Fila de Aprovação</div>
          <div className="mt-0.5 text-[11px] text-muted">
            Mensagens geradas por IA aguardando revisão antes de entrar na fila de envio
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={filtroCanal} onChange={(event) => setFiltroCanal(event.target.value)} className="w-36">
            <option value="">Todos os canais</option>
            <option value="email">E-mail</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="linkedin">LinkedIn</option>
          </Select>
          <Button size="sm" variant="violet" disabled={itens.length === 0} onClick={aprovarTudoVisivel}>
            Aprovar todas ({itens.length})
          </Button>
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}
      {mensagem && <div className="mb-4 text-[12px] text-green">{mensagem}</div>}

      <div className="flex flex-col gap-3">
        {itens.map((item) => (
          <Card key={item.aprovacao_id}>
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge tone={toneCanal(item.canal)}>{item.canal}</Badge>
                <span className="text-[11px] text-muted">conta #{item.conta_id} · decisor #{item.decisor_id}</span>
              </div>
              <span className="text-[10px] text-muted">{new Date(item.criado_em).toLocaleString("pt-BR")}</span>
            </div>
            <Textarea
              rows={4}
              defaultValue={item.conteudo}
              onChange={(event) =>
                setTextoEditado((atual) => ({ ...atual, [item.aprovacao_id]: event.target.value }))
              }
            />
            <div className="mt-2 flex justify-end gap-2">
              {textoEditado[item.aprovacao_id] !== undefined &&
                textoEditado[item.aprovacao_id] !== item.conteudo && (
                  <Button size="sm" variant="ghost" onClick={() => salvarEdicao(item)}>
                    Salvar edição
                  </Button>
                )}
              <Button size="sm" variant="danger" onClick={() => rejeitar(item.aprovacao_id)}>
                Rejeitar
              </Button>
              <Button size="sm" variant="green" onClick={() => aprovar(item.aprovacao_id)}>
                Aprovar
              </Button>
            </div>
          </Card>
        ))}
        {itens.length === 0 && (
          <Card>
            <div className="text-center text-[12px] text-muted">Nenhuma mensagem pendente de aprovação.</div>
          </Card>
        )}
      </div>
    </div>
  );
}
