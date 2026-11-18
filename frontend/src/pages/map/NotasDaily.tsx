import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { formatarData } from "@/lib/inadimplencia";

interface Nota {
  id: number;
  texto: string;
  exibir_em: string;
  concluida_em: string | null;
}

interface RespostaNotas {
  hoje: string;
  destaque: Nota[];
  agendadas: Nota[];
  historico: Nota[];
}

function somarDia(iso: string): string {
  const [ano, mes, dia] = iso.split("-").map(Number);
  const data = new Date(Date.UTC(ano, mes - 1, dia + 1));
  return data.toISOString().slice(0, 10);
}

/** Anotações da daily do gestor (pedido do PO, 18/11/2026). Escreve hoje, a nota volta em destaque no topo do MAP no dia seguinte (ou na data escolhida)
 * e fica ali até ele marcar como vista. Só quem escreveu vê as próprias notas. */
export function NotasDaily() {
  const [dados, setDados] = useState<RespostaNotas | null>(null);
  const [texto, setTexto] = useState("");
  const [data, setData] = useState("");
  const [aberto, setAberto] = useState(false);
  const [verAgendadas, setVerAgendadas] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const resposta = await api.get<RespostaNotas>("/map/notas-daily");
      setDados(resposta);
      setData((atual) => atual || somarDia(resposta.hoje));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as anotações da daily.");
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function salvar(evento: FormEvent) {
    evento.preventDefault();
    if (!texto.trim()) return;
    setSalvando(true);
    setErro(null);
    try {
      await api.post("/map/notas-daily", { texto: texto.trim(), exibir_em: data || null });
      setTexto("");
      setData(dados ? somarDia(dados.hoje) : "");
      setAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar a anotação.");
    } finally {
      setSalvando(false);
    }
  }

  async function marcarVista(nota: Nota) {
    try {
      await api.put(`/map/notas-daily/${nota.id}/concluir`, { concluida: true });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível marcar a anotação.");
    }
  }

  async function excluir(nota: Nota) {
    if (!window.confirm("Excluir esta anotação?")) return;
    try {
      await api.delete(`/map/notas-daily/${nota.id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a anotação.");
    }
  }

  if (!dados) return erro ? <Card className="p-3 text-[12px] text-red">{erro}</Card> : null;

  return (
    <div className="space-y-2">
      {dados.destaque.length > 0 && (
        <Card className="border-amber/40 bg-amber/5 p-4">
          <div className="mb-2 text-[11px] font-bold tracking-wide text-amber uppercase">📌 Anotações da sua daily para hoje</div>
          <ul className="space-y-2">
            {dados.destaque.map((nota) => (
              <li key={nota.id} className="flex flex-wrap items-start justify-between gap-2 border-t border-amber/20 pt-2 first:border-t-0 first:pt-0">
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] whitespace-pre-wrap">{nota.texto}</div>
                  {nota.exibir_em < dados.hoje && <div className="mt-0.5 text-[10px] text-muted">Marcada para {formatarData(nota.exibir_em)}</div>}
                </div>
                <div className="flex gap-1.5">
                  <Button type="button" size="sm" variant="ghost" onClick={() => marcarVista(nota)}>Marcar como vista</Button>
                  <Button type="button" size="sm" variant="danger" onClick={() => excluir(nota)}>Excluir</Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3 text-[11px]">
        <button type="button" onClick={() => setAberto((v) => !v)} className="text-cyan hover:underline">
          {aberto ? "Fechar anotação da daily" : "✏️ Anotar da daily"}
        </button>
        {dados.agendadas.length > 0 && (
          <button type="button" onClick={() => setVerAgendadas((v) => !v)} className="text-muted hover:text-cyan">
            {verAgendadas ? "Esconder" : "Ver"} anotações agendadas ({dados.agendadas.length})
          </button>
        )}
      </div>

      {aberto && (
        <Card className="p-4">
          <form onSubmit={salvar} className="space-y-2">
            <Textarea label="Anotação" rows={3} maxLength={4000} value={texto} onChange={(e) => setTexto(e.target.value)}
              placeholder="O que você quer lembrar na próxima daily?" />
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-44">
                <Input label="Mostrar em" type="date" min={dados.hoje} value={data} onChange={(e) => setData(e.target.value)} />
              </div>
              <Button type="submit" disabled={salvando || !texto.trim()}>{salvando ? "Salvando…" : "Salvar anotação"}</Button>
              <span className="text-[10px] text-muted">Por padrão, amanhã. Só você vê as suas anotações.</span>
            </div>
          </form>
        </Card>
      )}

      {verAgendadas && dados.agendadas.length > 0 && (
        <Card className="p-4">
          <ul className="space-y-1.5 text-[12px]">
            {dados.agendadas.map((nota) => (
              <li key={nota.id} className="flex items-start justify-between gap-2">
                <span className="min-w-0 flex-1 whitespace-pre-wrap"><span className="text-muted">{formatarData(nota.exibir_em)} · </span>{nota.texto}</span>
                <button type="button" onClick={() => excluir(nota)} className="text-[11px] text-red hover:underline">Excluir</button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {erro && <div className="text-[11px] text-red">{erro}</div>}
    </div>
  );
}
