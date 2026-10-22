import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { api, mensagemErro } from "@/lib/api";

import { dataVencimento, reais } from "./formatos";

export interface Pacote {
  codigo: string;
  nome: string;
  creditos: number | null;
  status: string;
  preco_unitario_brl: string | null;
  preco_total_brl: string | null;
  checkout_automatico: boolean;
  sob_negociacao: boolean;
}

interface Catalogo {
  pacotes: Pacote[];
  expira_em_previsto: string;
  compra_disponivel?: boolean;
  motivos?: { codigo: string; mensagem: string }[];
}

interface Compra {
  id: number;
  pacote: string;
  creditos: number;
  preco_total_brl: string;
  status: string;
  expira_em_previsto: string;
  expira_em: string | null;
  url_checkout: string | null;
  criado_em: string;
  situacao: string | null;
  situacao_rotulo: string | null;
  nota: { status: string; numero: string | null } | null;
}

const TOM_COMPRA: Record<string, "green" | "amber" | "red" | "muted"> = { APROVADA: "green", PENDENTE: "amber", REJEITADA: "red" };

/** Compra de créditos de enriquecimento adicionais (só administradores). O saldo comprado é separado da franquia, não aumenta nenhum limite do plano e
 * vale 30 dias a partir da confirmação do pagamento; enquanto vale, o limite de créditos por pesquisa passa a ser o do pacote. A data é mostrada ANTES da compra e exige ciência explícita. O crédito só entra quando o pagamento é confirmado pelo servidor. */
export function PacotesAdicionais({ onComprado }: { onComprado?: () => void }) {
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null);
  const [compras, setCompras] = useState<Compra[]>([]);
  const [ciente, setCiente] = useState(false);
  const [comprando, setComprando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function carregar() {
    api.get<Catalogo>("/pesquisas-decisores/pacotes").then(setCatalogo).catch((e) => setErro(mensagemErro(e, "Não foi possível carregar os pacotes.")));
    api.get<Compra[]>("/pesquisas-decisores/compras").then(setCompras).catch(() => setCompras([]));
  }
  useEffect(carregar, []);

  async function comprar(codigo: string) {
    setComprando(codigo);
    setErro(null);
    try {
      const compra = await api.post<Compra>("/pesquisas-decisores/compras", { pacote: codigo, aceite_expiracao: ciente });
      onComprado?.();
      if (compra.url_checkout) window.location.assign(compra.url_checkout);
      else carregar();
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível iniciar a compra."));
    } finally {
      setComprando(null);
    }
  }

  if (!catalogo) return erro ? <div className="text-[12px] text-red">{erro}</div> : null;
  const bloqueada = catalogo.compra_disponivel === false;
  const vence = dataVencimento(catalogo.expira_em_previsto);

  return (
    <Card>
      <SectionLabel>Créditos adicionais</SectionLabel>
      <p className="mb-2 text-[12px] text-muted">
        Saldo separado da sua franquia. Enquanto houver crédito do pacote, o seu limite de créditos por pesquisa passa a ser o do pacote comprado (por exemplo, 3.000),
        mesmo que a franquia do plano seja menor; quando os créditos acabarem ou o prazo vencer, volta ao limite do plano.{" "}
        <strong className="text-text">Se comprados agora, valem 30 dias e vencem em {vence}</strong> e não acumulam.
      </p>
      {bloqueada && (
        <div className="mb-2 rounded-md bg-surf2 p-2 text-[12px] text-amber">
          <p className="font-semibold">A compra está indisponível agora:</p>
          <ul className="list-disc pl-4">
            {(catalogo.motivos ?? []).map((m) => (
              <li key={m.codigo}>{m.mensagem}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-5">
        {catalogo.pacotes.map((p) => (
          <div key={p.codigo} className="flex flex-col justify-between rounded-md bg-surf2 p-2.5 text-[12px]">
            <div>
              <p className="font-semibold">{p.nome}</p>
              {p.sob_negociacao ? (
                <p className="mt-1 text-muted">Sob negociação. Fale com o comercial para uma cotação.</p>
              ) : (
                <>
                  <p className="text-[18px] font-bold tabular-nums">{reais(p.preco_total_brl)}</p>
                  <p className="text-muted">{reais(p.preco_unitario_brl)} por crédito</p>
                </>
              )}
            </div>
            {p.checkout_automatico && (
              <Button className="mt-2" size="sm" disabled={bloqueada || !ciente || comprando !== null} onClick={() => comprar(p.codigo)}>
                {comprando === p.codigo ? "Abrindo o pagamento..." : "Comprar"}
              </Button>
            )}
          </div>
        ))}
      </div>
      <label className="mt-2 flex items-start gap-2 text-[12px]">
        <input type="checkbox" className="mt-0.5" checked={ciente} onChange={(ev) => setCiente(ev.target.checked)} />
        <span>Estou ciente de que os créditos adicionais vencem em {vence} e não acumulam para o mês seguinte.</span>
      </label>
      {erro && <p className="mt-1 text-[12px] text-red">{erro}</p>}
      {compras.length > 0 && (
        <table className="mt-3 w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-1.5 text-left">Pedido</th>
              <th className="p-1.5 text-right">Créditos</th>
              <th className="p-1.5 text-right">Valor</th>
              <th className="p-1.5 text-left">Situação</th>
              <th className="p-1.5 text-left">Vence em</th>
              <th className="p-1.5 text-left">Nota fiscal</th>
            </tr>
          </thead>
          <tbody>
            {compras.map((c) => (
              <tr key={c.id} className="border-b border-border">
                <td className="p-1.5 text-muted">{new Date(c.criado_em).toLocaleDateString("pt-BR")}</td>
                <td className="p-1.5 text-right tabular-nums">{c.creditos}</td>
                <td className="p-1.5 text-right tabular-nums">{reais(c.preco_total_brl)}</td>
                <td className="p-1.5">
                  <Badge tone={TOM_COMPRA[c.status] ?? "muted"}>{c.status === "PENDENTE" ? "aguardando pagamento" : c.status.toLowerCase()}</Badge>
                </td>
                <td className="p-1.5 text-muted">{dataVencimento(c.expira_em ?? c.expira_em_previsto)}</td>
                <td className="p-1.5 text-muted">{c.status !== "APROVADA" ? "—" : c.nota?.status === "EMITIDA" ? `NF ${c.nota.numero}` : "nota a emitir"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
