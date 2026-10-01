import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api, mensagemErro } from "@/lib/api";

interface Aliquotas {
  impostos: number | null;
  infraestrutura: number | null;
  versao: number;
  comissoes_recalculadas?: number;
}

const pct = (valor: number | null) =>
  valor === null ? "não definido" : `${(valor * 100).toLocaleString("pt-BR")}%`;

/** D-073: a comissão de todo representante (planos privados e Government) é calculada sobre o lucro líquido do
 * recebimento — valor recebido menos impostos e infraestrutura. Sem as duas alíquotas, as comissões aguardam. */
export function BaseLiquidaComissao() {
  const [aliquotas, setAliquotas] = useState<Aliquotas | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Aliquotas>("/representantes/base-liquida-comissao")
      .then(setAliquotas)
      .catch(() => setAliquotas(null));
  }, []);

  async function salvar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    const f = new FormData(formulario);
    try {
      const novas = await api.put<Aliquotas>(
        "/representantes/base-liquida-comissao",
        {
          impostos: Number(f.get("impostos")) / 100,
          infraestrutura: Number(f.get("infraestrutura")) / 100,
          motivo: String(f.get("motivo")),
        },
      );
      setAliquotas(novas);
      setMensagem(
        `Salvo. ${novas.comissoes_recalculadas ?? 0} comissão(ões) aguardando foram calculadas.`,
      );
      formulario.reset();
    } catch (error) {
      setMensagem(mensagemErro(error, "Não foi possível salvar as alíquotas."));
    }
  }

  if (!aliquotas) return null;
  const pendente =
    aliquotas.impostos === null || aliquotas.infraestrutura === null;
  return (
    <Card data-testid="base-liquida-comissao">
      <SectionLabel>
        Base das comissões — lucro líquido (todas as vendas)
      </SectionLabel>
      <div className="text-[12px] text-muted">
        Comissão = (valor recebido − impostos − infraestrutura) × taxa do
        representante. Impostos: {pct(aliquotas.impostos)} · Infraestrutura:{" "}
        {pct(aliquotas.infraestrutura)} (versão {aliquotas.versao}).
        {pendente && (
          <span className="text-amber">
            {" "}
            Enquanto não forem definidas, as comissões ficam aguardando e não
            são repassadas.
          </span>
        )}
      </div>
      <form
        onSubmit={salvar}
        className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-4"
      >
        <Input
          name="impostos"
          type="number"
          min={0}
          max={99}
          step="0.01"
          required
          placeholder="Impostos (%)"
        />
        <Input
          name="infraestrutura"
          type="number"
          min={0}
          max={99}
          step="0.01"
          required
          placeholder="Infraestrutura (%)"
        />
        <Input name="motivo" required placeholder="Motivo (auditoria)" />
        <Button type="submit" size="sm">
          Salvar alíquotas
        </Button>
      </form>
      {mensagem && (
        <div className="mt-1.5 text-[11px] text-muted">{mensagem}</div>
      )}
    </Card>
  );
}
