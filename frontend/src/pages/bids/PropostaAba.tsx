import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { api, getBlob, mensagemErro } from "@/lib/api";

interface Esboco {
  itens: {
    requisito_id: number;
    categoria: string;
    requisito: string;
    obrigatorio: boolean | null;
    conformidade: string | null;
    resposta: string | null;
  }[];
  pendencias: { requisito_id: number; tipo: string; mensagem: string }[];
  anexos: { id: number; nome: string; valido_ate: string | null }[];
  prontidao: number | null;
  uso_ia: string;
}

/** Apoio à proposta (Phase C): esboço determinístico, sem IA. Recarrega
 * quando o workspace muda (`versao`). */
export function PropostaAba({
  licitacaoId,
  versao,
}: {
  licitacaoId: number;
  versao: unknown;
}) {
  const [esboco, setEsboco] = useState<Esboco | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Esboco>(`/bids/licitacoes/${licitacaoId}/proposta`)
      .then(setEsboco)
      .catch((error) =>
        setErro(mensagemErro(error, "Não foi possível montar o esboço.")),
      );
  }, [licitacaoId, versao]);

  async function baixar() {
    const blob = await getBlob(
      `/bids/licitacoes/${licitacaoId}/proposta?formato=markdown`,
    );
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `proposta-${licitacaoId}.md`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  if (!esboco)
    return (
      <div className="text-[12px] text-muted">
        {erro ?? "Montando esboço..."}
      </div>
    );

  return (
    <div
      className="grid grid-cols-1 gap-3.5 lg:grid-cols-2"
      data-testid="proposta-aba"
    >
      <Card>
        <SectionLabel>Prontidão</SectionLabel>
        <div className="text-[12px]">
          {esboco.prontidao === null
            ? "Sem requisitos: confirme os requisitos para montar a proposta."
            : `${Math.round(esboco.prontidao * 100)}% dos itens sem pendência`}
        </div>
        <div className="mt-1 text-[10px] text-muted">{esboco.uso_ia}</div>
        <Button className="mt-2" size="sm" variant="ghost" onClick={baixar}>
          Baixar esboço (.md)
        </Button>
        {esboco.anexos.length > 0 && (
          <div className="mt-3 text-[11px]">
            <div className="text-muted">Documentos do cofre a anexar:</div>
            {esboco.anexos.map((a) => (
              <div key={a.id}>• {a.nome}</div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <SectionLabel>Pendências antes de enviar</SectionLabel>
        <div className="flex flex-col gap-1 text-[11px]">
          {esboco.pendencias.map((p, i) => (
            <div
              key={`${p.requisito_id}-${p.tipo}-${i}`}
              className="flex items-start gap-2"
            >
              <Badge tone={p.tipo === "COMPROVAR" ? "red" : "amber"}>
                {p.tipo}
              </Badge>
              <span>{p.mensagem}</span>
            </div>
          ))}
          {esboco.pendencias.length === 0 && (
            <div className="text-muted">Nenhuma pendência.</div>
          )}
        </div>
      </Card>
      <Card className="lg:col-span-2">
        <SectionLabel>Itens</SectionLabel>
        <div className="flex flex-col gap-1 text-[11px]">
          {esboco.itens.map((item) => (
            <div
              key={item.requisito_id}
              className="border-b border-border py-1"
            >
              <span className="text-muted">{item.categoria}:</span>{" "}
              {item.requisito}{" "}
              {item.obrigatorio === true && (
                <Badge tone="violet">Obrigatório</Badge>
              )}{" "}
              {item.conformidade && <Badge>{item.conformidade}</Badge>}
              <div className="text-muted">
                Resposta: {item.resposta ?? "pendente"}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
