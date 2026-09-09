import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";

interface ResultadoBusca {
  tipo: "conta" | "negocio" | "proposta" | "cadencia" | "tenant";
  id: number | string;
  titulo: string;
  subtitulo: string | null;
  rota: string;
}

const ROTULO_GRUPO: Record<ResultadoBusca["tipo"], string> = {
  conta: "Empresas",
  negocio: "Oportunidades",
  proposta: "Propostas",
  cadencia: "Cadências",
  tenant: "Tenants",
};

const ORDEM_GRUPOS: ResultadoBusca["tipo"][] = ["conta", "negocio", "proposta", "cadencia", "tenant"];

interface BuscaGlobalProps {
  open: boolean;
  onClose: () => void;
}

export function BuscaGlobal({ open, onClose }: BuscaGlobalProps) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState<ResultadoBusca[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [indiceSelecionado, setIndiceSelecionado] = useState(0);
  const controladorAtualRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    setTermo("");
    setResultados([]);
    setErro(null);
    setIndiceSelecionado(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    controladorAtualRef.current?.abort();

    const termoLimpo = termo.trim();
    if (!termoLimpo) {
      setResultados([]);
      setBuscando(false);
      return;
    }

    const controlador = new AbortController();
    controladorAtualRef.current = controlador;
    const temporizador = setTimeout(async () => {
      setBuscando(true);
      setErro(null);
      try {
        const dados = await api.get<ResultadoBusca[]>(`/busca?q=${encodeURIComponent(termoLimpo)}`, {
          signal: controlador.signal,
        });
        setResultados(dados);
        setIndiceSelecionado(0);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setErro(error instanceof ApiError ? error.message : "Não foi possível buscar agora.");
      } finally {
        setBuscando(false);
      }
    }, 300);

    return () => clearTimeout(temporizador);
  }, [termo, open]);

  function irParaResultado(resultado: ResultadoBusca) {
    onClose();
    navigate(resultado.rota);
  }

  function aoTeclar(evento: KeyboardEvent<HTMLInputElement>) {
    if (evento.key === "Escape") {
      onClose();
      return;
    }
    if (evento.key === "ArrowDown") {
      evento.preventDefault();
      setIndiceSelecionado((atual) => Math.min(atual + 1, resultados.length - 1));
      return;
    }
    if (evento.key === "ArrowUp") {
      evento.preventDefault();
      setIndiceSelecionado((atual) => Math.max(atual - 1, 0));
      return;
    }
    if (evento.key === "Enter") {
      evento.preventDefault();
      const resultado = resultados[indiceSelecionado];
      if (resultado) irParaResultado(resultado);
    }
  }

  if (!open) return null;

  const grupos = ORDEM_GRUPOS.map((tipo) => ({
    tipo,
    itens: resultados.filter((resultado) => resultado.tipo === tipo),
  })).filter((grupo) => grupo.itens.length > 0);

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[12vh]">
      <div className="absolute inset-0 bg-slate-950/70" onClick={onClose} />
      <div className="relative flex max-h-[70vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border2 bg-surf shadow-2xl">
        <div className="border-b border-border p-3">
          <Input
            value={termo}
            onChange={(event) => setTermo(event.target.value)}
            onKeyDown={aoTeclar}
            placeholder="Buscar empresa, oportunidade, proposta, cadência ou tenant..."
            autoFocus
          />
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {buscando && <div className="p-3 text-[12px] text-muted">Buscando...</div>}
          {erro && <div className="p-3 text-[12px] text-red">{erro}</div>}
          {!buscando && !erro && termo.trim() && resultados.length === 0 && (
            <div className="p-3 text-[12px] text-muted">Nenhum resultado pra "{termo.trim()}".</div>
          )}
          {!termo.trim() && (
            <div className="p-3 text-[12px] text-muted">
              Digite pra buscar em empresas, oportunidades, propostas, cadências
              {resultados.length === 0 ? " e tenants." : "."}
            </div>
          )}
          {grupos.map((grupo) => (
            <div key={grupo.tipo} className="mb-2">
              <div className="px-2 py-1 text-[10px] tracking-wide text-muted uppercase">{ROTULO_GRUPO[grupo.tipo]}</div>
              {grupo.itens.map((item) => {
                const indiceGlobal = resultados.indexOf(item);
                const selecionado = indiceGlobal === indiceSelecionado;
                return (
                  <button
                    key={`${item.tipo}-${item.id}`}
                    type="button"
                    onMouseEnter={() => setIndiceSelecionado(indiceGlobal)}
                    onClick={() => irParaResultado(item)}
                    className={`flex w-full flex-col rounded-lg px-3 py-2 text-left transition-colors ${
                      selecionado ? "bg-cyan/15" : "hover:bg-white/5"
                    }`}
                  >
                    <span className="text-[13px] font-semibold text-text">{item.titulo}</span>
                    {item.subtitulo && <span className="text-[11px] text-muted">{item.subtitulo}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
