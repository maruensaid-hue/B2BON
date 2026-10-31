import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { rotuloDaConta } from "@/lib/conta";

export interface ContaResumo {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  icp_id: number | null;
}

interface PaginaContas {
  itens: ContaResumo[];
  total: number;
  limite: number;
  offset: number;
}

interface Props {
  // Nome do campo escondido que leva o id escolhido: os formulários que leem `FormData` recebem `conta_id` como antes.
  name?: string;
  // Empresa já escolhida ao abrir (ex.: a empresa atual do contato).
  valorInicial?: { id: number; rotulo: string } | null;
  // Só sugere empresas deste ICP.
  icpId?: number | null;
  placeholder?: string;
  // Chamado com a empresa escolhida, ou `null` quando a pessoa volta a digitar (a escolha anterior deixa de valer).
  onSelecionar?: (conta: ContaResumo | null) => void;
}

const LIMITE_SUGESTOES = 20;
const ATRASO_BUSCA_MS = 250;

// Escolha de empresa com busca no servidor: o tenant pode ter milhares de contas, então a lista nunca é carregada inteira.
// Busca ao focar e a cada pausa na digitação, mostra até 20 sugestões e avisa quando há mais.
export function SeletorConta({ name, valorInicial = null, icpId = null, placeholder, onSelecionar }: Props) {
  const [texto, setTexto] = useState(valorInicial?.rotulo ?? "");
  const [selecionadaId, setSelecionadaId] = useState<number | null>(valorInicial?.id ?? null);
  const [sugestoes, setSugestoes] = useState<ContaResumo[]>([]);
  const [total, setTotal] = useState(0);
  const [aberto, setAberto] = useState(false);
  const [buscando, setBuscando] = useState(false);
  const [falhou, setFalhou] = useState(false);
  // Respostas fora de ordem (a de uma digitação antiga chegando depois) são descartadas pelo número do pedido.
  const pedidoAtual = useRef(0);

  useEffect(() => {
    if (!aberto) return;
    const numero = ++pedidoAtual.current;
    const espera = setTimeout(() => {
      setBuscando(true);
      setFalhou(false);
      const parametros = new URLSearchParams({ limite: String(LIMITE_SUGESTOES) });
      if (texto.trim()) parametros.set("busca", texto.trim());
      if (icpId !== null) parametros.set("icp_id", String(icpId));
      api
        .get<PaginaContas>(`/contas/pesquisa?${parametros.toString()}`)
        .then((pagina) => {
          if (numero !== pedidoAtual.current) return;
          setSugestoes(pagina.itens);
          setTotal(pagina.total);
        })
        .catch(() => {
          if (numero !== pedidoAtual.current) return;
          setSugestoes([]);
          setTotal(0);
          setFalhou(true);
        })
        .finally(() => {
          if (numero === pedidoAtual.current) setBuscando(false);
        });
    }, ATRASO_BUSCA_MS);
    return () => clearTimeout(espera);
  }, [texto, icpId, aberto]);

  function escolher(conta: ContaResumo) {
    setSelecionadaId(conta.id);
    setTexto(rotuloDaConta(conta));
    setAberto(false);
    onSelecionar?.(conta);
  }

  const semResultado = aberto && !buscando && !falhou && sugestoes.length === 0 && texto.trim() !== "";

  return (
    <div className="relative">
      <Input
        value={texto}
        onChange={(event) => {
          setTexto(event.target.value);
          setSelecionadaId(null);
          setAberto(true);
          onSelecionar?.(null);
        }}
        onFocus={() => setAberto(true)}
        onBlur={() => setTimeout(() => setAberto(false), 150)}
        autoComplete="off"
        placeholder={placeholder ?? "Digite o nome da empresa..."}
      />
      {name && <input type="hidden" name={name} value={selecionadaId ?? ""} />}
      {aberto && sugestoes.length > 0 && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border bg-surf shadow-lg">
          {sugestoes.map((conta) => (
            <button
              key={conta.id}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => escolher(conta)}
              className="block w-full px-3 py-2 text-left text-[12px] hover:bg-surf2"
            >
              {rotuloDaConta(conta)}
            </button>
          ))}
          {total > sugestoes.length && (
            <div className="border-t border-border px-3 py-1.5 text-[11px] text-muted">
              Mostrando {sugestoes.length} de {total}. Digite mais do nome para refinar.
            </div>
          )}
        </div>
      )}
      {semResultado && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-surf p-2 text-[12px] text-muted shadow-lg">
          Nenhuma conta encontrada com esse nome.
        </div>
      )}
      {aberto && falhou && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-surf p-2 text-[12px] text-red shadow-lg">
          Não foi possível buscar as contas.
        </div>
      )}
      {!aberto && texto.trim() !== "" && selecionadaId === null && (
        <div className="mt-1 text-[11px] text-muted">Escolha uma das empresas sugeridas.</div>
      )}
    </div>
  );
}
