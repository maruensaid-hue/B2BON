import { Badge } from "@/components/ui/Badge";
import { brl } from "@/lib/aiCredits";
import {
  linhasEntitlements,
  type CatalogoGoverno,
  type OfertaGoverno,
} from "@/lib/catalogo";

const TIER: Record<string, string> = {
  "B2B ON Government Department": "Department",
  "B2B ON Government Professional": "Professional",
  "B2B ON Government Enterprise": "Enterprise",
};

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-[12px]">
      <span className="text-muted">{rotulo}</span>
      <span className="font-semibold whitespace-nowrap text-text">{valor}</span>
    </div>
  );
}

function OfertaCard({ oferta }: { oferta: OfertaGoverno }) {
  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border bg-surf p-4.5 ${
        oferta.recomendado
          ? "border-cyan shadow-[0_0_20px_rgba(0,194,255,0.12)]"
          : "border-border"
      }`}
      data-testid="oferta-governo"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-head text-[15px] font-bold text-text uppercase">
          {TIER[oferta.nome] ?? oferta.nome}
        </span>
        {oferta.recomendado && <Badge tone="cyan">Recomendado</Badge>}
      </div>
      <div className="text-[11px] text-muted">{oferta.nome}</div>
      <div className="flex flex-col gap-1 border-t border-dashed border-border2 pt-2">
        <Linha rotulo="Licença institucional" valor={brl(oferta.licenca)} />
        <Linha rotulo="Implantação" valor={brl(oferta.implantacao)} />
        <Linha rotulo="Subscrição anual" valor={brl(oferta.assinatura_anual)} />
      </div>
      <div className="flex items-baseline justify-between gap-2 border-t border-dashed border-border2 pt-2">
        <span className="text-[12px] font-semibold text-text">
          Contratação inicial
        </span>
        <span className="font-head text-[18px] font-bold text-text">
          {brl(oferta.contratacao_inicial)}
        </span>
      </div>
      <div
        className="flex flex-col gap-0.5 border-t border-dashed border-border2 pt-2"
        data-testid="entitlements-governo"
      >
        {linhasEntitlements(oferta.entitlements).map(([rotulo, valor]) => (
          <div key={rotulo} className="flex justify-between gap-2 text-[11px]">
            <span className="text-muted">{rotulo}</span>
            <span className="text-text">{valor}</span>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-muted">
        {oferta.creditos_ia_anuais !== null
          ? `${oferta.creditos_ia_anuais.toLocaleString("pt-BR")} AI Credits/ano`
          : "AI Credits conforme contrato"}
      </div>
      <a
        href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(`Interesse: ${oferta.nome}`)}`}
        className="mt-1 text-[12px] font-semibold text-cyan hover:underline"
      >
        Falar com o comercial →
      </a>
    </div>
  );
}

/** Seção "B2B ON Government" da página de preços (D-072): valores do catálogo central (`GET /catalogo`),
 * por componente e sem "/mês". */
export function SecaoGoverno({ governo }: { governo: CatalogoGoverno }) {
  if (governo.planos.length === 0) return null;
  return (
    <section id="government" data-testid="secao-governo" className="mb-14">
      <div className="mb-6 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
          Setor público
        </div>
        <div className="mt-1.5 font-head text-xl font-bold text-text">
          {governo.nome}
        </div>
        <div className="mx-auto mt-1.5 max-w-[640px] text-[12px] text-muted">
          {governo.descricao}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {governo.planos.map((oferta) => (
          <OfertaCard key={oferta.id} oferta={oferta} />
        ))}
      </div>
      <div className="mt-5 flex flex-col gap-1.5 rounded-xl border border-border bg-surf p-4 text-[12px] leading-relaxed text-muted">
        <div className="font-semibold text-text">{governo.composicao}</div>
        <div>{governo.renovacao}</div>
        <div>{governo.adaptacao}</div>
        <div>{governo.so_assinatura}</div>
      </div>
    </section>
  );
}
