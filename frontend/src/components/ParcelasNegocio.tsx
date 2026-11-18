import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { formatarData, formatarMoeda } from "@/lib/inadimplencia";

interface Parcela {
  id: number;
  numero: number;
  valor: number;
  vencimento: string;
  pago_em: string | null;
  observacao: string | null;
  em_atraso: boolean;
  dias_atraso: number;
}

interface RespostaParcelas {
  ganho: boolean;
  valor_negocio: number;
  parcelas: Parcela[];
}

function hojeLocal(): string {
  const agora = new Date();
  return `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}-${String(agora.getDate()).padStart(2, "0")}`;
}

/** Pagamentos combinados com o cliente num negócio ganho (pedido do PO, 18/11/2026). O vendedor lança valor e vencimento; ao receber, marca "pago".
 * Parcela vencida e não paga aparece no quadro "Clientes inadimplentes" do MAP. Autocontido como `PropostasNegocio`: só recebe o id do negócio. */
export function ParcelasNegocio({ negocioId }: { negocioId: number }) {
  const [dados, setDados] = useState<RespostaParcelas | null>(null);
  const [valor, setValor] = useState("");
  const [vencimento, setVencimento] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      setDados(await api.get<RespostaParcelas>(`/crm/negocios/${negocioId}/parcelas`));
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as parcelas.");
    }
  }

  useEffect(() => {
    carregar();
  }, [negocioId]);

  async function lancar(evento: FormEvent) {
    evento.preventDefault();
    const numero = Number(valor.replace(/\./g, "").replace(",", "."));
    if (!numero || numero <= 0 || !vencimento) {
      setErro("Informe o valor e o vencimento da parcela.");
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      await api.post(`/crm/negocios/${negocioId}/parcelas`, { valor: numero, vencimento, observacao: observacao.trim() || null });
      setValor("");
      setVencimento("");
      setObservacao("");
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível lançar a parcela.");
    } finally {
      setSalvando(false);
    }
  }

  async function alternarPago(parcela: Parcela) {
    setErro(null);
    try {
      await api.put(`/crm/negocios/${negocioId}/parcelas/${parcela.id}`, {
        valor: parcela.valor,
        vencimento: parcela.vencimento,
        observacao: parcela.observacao,
        pago_em: parcela.pago_em ? null : hojeLocal(),
      });
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível atualizar a parcela.");
    }
  }

  async function excluir(parcela: Parcela) {
    if (!window.confirm(`Excluir a parcela ${parcela.numero} (${formatarMoeda(parcela.valor)})?`)) return;
    setErro(null);
    try {
      await api.delete(`/crm/negocios/${negocioId}/parcelas/${parcela.id}`);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível excluir a parcela.");
    }
  }

  if (!dados) {
    return <div className="text-[12px] text-muted">{erro ?? "Carregando parcelas…"}</div>;
  }

  const total = dados.parcelas.reduce((soma, p) => soma + p.valor, 0);
  const recebido = dados.parcelas.filter((p) => p.pago_em).reduce((soma, p) => soma + p.valor, 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[13px] font-bold">Parcelas a receber</div>
        {dados.parcelas.length > 0 && (
          <div className="text-[11px] text-muted">
            Combinado {formatarMoeda(total)} · recebido {formatarMoeda(recebido)}
            {Math.abs(total - dados.valor_negocio) > 0.009 && ` · valor do negócio ${formatarMoeda(dados.valor_negocio)}`}
          </div>
        )}
      </div>

      {!dados.ganho ? (
        <div className="text-[12px] text-muted">As parcelas são lançadas depois que o negócio é marcado como ganho.</div>
      ) : (
        <>
          {dados.parcelas.length === 0 ? (
            <div className="text-[12px] text-muted">
              Nenhuma parcela lançada. Registre aqui o que foi combinado com o cliente: a parcela que vencer sem pagamento aparece no MAP, em Clientes
              inadimplentes.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10px] tracking-wide text-muted uppercase">
                    <th className="py-1.5 pr-2">#</th>
                    <th className="py-1.5 pr-2">Valor</th>
                    <th className="py-1.5 pr-2">Vencimento</th>
                    <th className="py-1.5 pr-2">Situação</th>
                    <th className="py-1.5 pr-2">Observação</th>
                    <th className="py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {dados.parcelas.map((parcela) => (
                    <tr key={parcela.id} className="border-t border-border">
                      <td className="py-1.5 pr-2">{parcela.numero}</td>
                      <td className="py-1.5 pr-2">{formatarMoeda(parcela.valor)}</td>
                      <td className="py-1.5 pr-2">{formatarData(parcela.vencimento)}</td>
                      <td className="py-1.5 pr-2">
                        {parcela.pago_em ? (
                          <Badge tone="green">Pago em {formatarData(parcela.pago_em)}</Badge>
                        ) : parcela.em_atraso ? (
                          <Badge tone="red">{parcela.dias_atraso} dia(s) em atraso</Badge>
                        ) : (
                          <Badge tone="muted">A vencer</Badge>
                        )}
                      </td>
                      <td className="py-1.5 pr-2 text-muted">{parcela.observacao ?? ""}</td>
                      <td className="py-1.5 text-right whitespace-nowrap">
                        <Button type="button" size="sm" variant="ghost" onClick={() => alternarPago(parcela)}>
                          {parcela.pago_em ? "Desfazer pagamento" : "Marcar pago"}
                        </Button>{" "}
                        <Button type="button" size="sm" variant="danger" onClick={() => excluir(parcela)}>
                          Excluir
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <form onSubmit={lancar} className="grid gap-2 sm:grid-cols-[1fr_1fr_2fr_auto] sm:items-end">
            <Input label="Valor (R$)" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="1.500,00" />
            <Input label="Vencimento" type="date" value={vencimento} onChange={(e) => setVencimento(e.target.value)} />
            <Input label="Observação (opcional)" value={observacao} maxLength={300} onChange={(e) => setObservacao(e.target.value)}
              placeholder="Ex.: boleto, 2ª de 3" />
            <Button type="submit" disabled={salvando}>{salvando ? "Lançando…" : "Lançar parcela"}</Button>
          </form>
        </>
      )}
      {erro && <div className="text-[11px] text-red">{erro}</div>}
    </div>
  );
}
