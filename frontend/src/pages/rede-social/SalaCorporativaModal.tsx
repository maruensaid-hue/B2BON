import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Canal {
  id: number;
  sala_id: number;
  tipo: string;
  nome: string | null;
  criado_em: string;
}

interface MensagemSala {
  id: number;
  canal_id: number;
  tenant_id_remetente: string;
  empresa_nome: string;
  texto: string;
  documento_url: string | null;
  criado_em: string;
}

const ROTULO_TIPO_CANAL: Record<string, string> = {
  GENERAL: "Geral",
  COMMERCIAL: "Comercial",
  TECHNICAL: "Técnico",
  LEGAL: "Jurídico",
  PROCUREMENT: "Compras",
  FINANCIAL: "Financeiro",
  SUPPORT: "Suporte",
  CUSTOM: "Personalizado",
};

const TIPOS_CANAL_DISPONIVEIS = Object.keys(ROTULO_TIPO_CANAL);

const INTERVALO_POLLING_SALA_MS = 8_000;

interface Props {
  salaId: number;
  nomeExibicao: string;
  onClose: () => void;
}

export function SalaCorporativaModal({ salaId, nomeExibicao, onClose }: Props) {
  const { usuario } = useAuth();
  const [canais, setCanais] = useState<Canal[]>([]);
  const [canalAtivoId, setCanalAtivoId] = useState<number | null>(null);
  const [mensagens, setMensagens] = useState<MensagemSala[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [criandoCanal, setCriandoCanal] = useState(false);
  const [novoCanalTipo, setNovoCanalTipo] = useState("COMMERCIAL");
  const [novoCanalNome, setNovoCanalNome] = useState("");

  async function carregarCanais() {
    try {
      const resposta = await api.get<Canal[]>(`/rede-social/salas/${salaId}/canais`);
      setCanais(resposta);
      if (canalAtivoId === null && resposta.length > 0) setCanalAtivoId(resposta[0].id);
    } catch {
      setErro("Não foi possível carregar os canais.");
    }
  }

  async function carregarMensagens(canalId: number) {
    try {
      setMensagens(await api.get<MensagemSala[]>(`/rede-social/salas/canais/${canalId}/mensagens`));
    } catch {
      setErro("Não foi possível carregar as mensagens.");
    }
  }

  useEffect(() => {
    carregarCanais();
  }, [salaId]);

  useEffect(() => {
    if (canalAtivoId === null) return;
    carregarMensagens(canalAtivoId);
    // Sem WebSocket/SSE (fora de escopo desta fase) — polling leve
    // enquanto a sala está aberta, mais frequente que o polling de
    // notificação por ser um contexto de chat ativo.
    const intervalo = setInterval(() => carregarMensagens(canalAtivoId), INTERVALO_POLLING_SALA_MS);
    return () => clearInterval(intervalo);
  }, [canalAtivoId]);

  async function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canalAtivoId === null) return;
    const formulario = event.currentTarget;
    const dados = new FormData(formulario);
    const texto = String(dados.get("texto") ?? "").trim();
    if (!texto) return;
    try {
      await api.post(`/rede-social/salas/canais/${canalAtivoId}/mensagens`, {
        texto,
        documento_url: String(dados.get("documento_url") || "") || null,
      });
      formulario.reset();
      await carregarMensagens(canalAtivoId);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível enviar a mensagem.");
    }
  }

  async function criarCanal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const canal = await api.post<Canal>(`/rede-social/salas/${salaId}/canais`, {
        tipo: novoCanalTipo,
        nome: novoCanalTipo === "CUSTOM" ? novoCanalNome.trim() || null : null,
      });
      setCanais((atual) => [...atual, canal]);
      setCanalAtivoId(canal.id);
      setCriandoCanal(false);
      setNovoCanalNome("");
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o canal.");
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[8vh]">
      <div className="absolute inset-0 bg-slate-950/70" onClick={onClose} />
      <div className="relative flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border2 bg-surf shadow-2xl">
        <div className="flex items-center justify-between border-b border-border p-3">
          <div className="font-head text-base font-bold text-text">Sala Corporativa — {nomeExibicao}</div>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-surf2 text-muted"
          >
            ✕
          </button>
        </div>

        <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 overflow-x-auto">
          {canais.map((canal) => (
            <button
              key={canal.id}
              onClick={() => setCanalAtivoId(canal.id)}
              className={`flex-shrink-0 rounded-full px-3 py-1 text-[11px] ${
                canalAtivoId === canal.id ? "bg-cyan text-white" : "bg-surf2 text-muted"
              }`}
            >
              {canal.tipo === "CUSTOM" && canal.nome ? canal.nome : ROTULO_TIPO_CANAL[canal.tipo] ?? canal.tipo}
            </button>
          ))}
          <button
            onClick={() => setCriandoCanal((atual) => !atual)}
            className="flex-shrink-0 rounded-full border border-border px-3 py-1 text-[11px] text-muted"
          >
            + Canal
          </button>
        </div>

        {criandoCanal && (
          <form onSubmit={criarCanal} className="flex items-center gap-2 border-b border-border px-3 py-2">
            <select
              value={novoCanalTipo}
              onChange={(event) => setNovoCanalTipo(event.target.value)}
              className="rounded-lg border border-border bg-surf2 px-2 py-1.5 text-[11px] text-text outline-none"
            >
              {TIPOS_CANAL_DISPONIVEIS.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {ROTULO_TIPO_CANAL[tipo]}
                </option>
              ))}
            </select>
            {novoCanalTipo === "CUSTOM" && (
              <Input
                value={novoCanalNome}
                onChange={(event) => setNovoCanalNome(event.target.value)}
                placeholder="Nome do canal"
                className="flex-1"
              />
            )}
            <Button type="submit" size="sm">
              Criar
            </Button>
          </form>
        )}

        {erro && <div className="px-3 pt-2 text-[12px] text-red">{erro}</div>}

        <div className="flex-1 overflow-y-auto p-3">
          <div className="flex flex-col gap-2">
            {mensagens.map((mensagem) => {
              const enviadaPorMim = mensagem.tenant_id_remetente === usuario?.tenant_id;
              return (
                <div
                  key={mensagem.id}
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-[12px] ${
                    enviadaPorMim ? "self-end bg-cyan/15 text-text" : "self-start bg-surf2 text-text"
                  }`}
                >
                  <div className="mb-0.5 text-[10px] text-muted">{mensagem.empresa_nome}</div>
                  {mensagem.texto}
                  {mensagem.documento_url && (
                    <a
                      href={mensagem.documento_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block text-cyan underline"
                    >
                      📎 {mensagem.documento_url}
                    </a>
                  )}
                </div>
              );
            })}
            {mensagens.length === 0 && <div className="text-[12px] text-muted">Nenhuma mensagem neste canal ainda.</div>}
          </div>
        </div>

        <form onSubmit={enviar} className="flex gap-2 border-t border-border p-3">
          <Input name="texto" placeholder="Escreva uma mensagem..." className="flex-1" />
          <Input name="documento_url" placeholder="URL de documento (opcional)" className="flex-1" />
          <Button type="submit" size="sm">
            Enviar
          </Button>
        </form>
      </div>
    </div>
  );
}
