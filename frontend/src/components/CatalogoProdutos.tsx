import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import {
  formatarLimite,
  ROTULO_DISPONIBILIDADE,
  ROTULO_LIMITE,
  ROTULO_RECURSO,
  TOM_DISPONIBILIDADE,
  type Catalogo,
} from "@/lib/catalogo";

/** Produtos e comparativo de recursos da página pública (Fase 14). Vem
 * do `GET /catalogo`: o estado de cada produto é o do backend, e nada em
 * beta, sob consulta ou em definição vira botão de compra. Preços
 * continuam nas seções de planos (não há segunda fonte de preço aqui). */
export function CatalogoProdutos() {
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null);

  useEffect(() => {
    api
      .get<Catalogo>("/catalogo")
      .then(setCatalogo)
      .catch(() => setCatalogo(null));
  }, []);

  if (!catalogo) return null;
  const suites = catalogo.planos.filter(
    (p) => p.categoria === "suite" && p.preco_mensal > 0,
  );

  return (
    <section data-testid="catalogo-produtos">
      <div className="mt-14 mb-8 text-center">
        <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
          Plataforma completa
        </div>
        <div className="mt-1.5 font-head text-xl font-bold text-text">
          Todos os produtos B2B ON
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {catalogo.produtos.map((produto) => (
          <div
            key={produto.id}
            className="flex flex-col gap-2 rounded-xl border border-border bg-surf p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-head text-[14px] font-bold text-text">
                {produto.nome}
              </span>
              <Badge tone={TOM_DISPONIBILIDADE[produto.disponibilidade]}>
                {ROTULO_DISPONIBILIDADE[produto.disponibilidade]}
              </Badge>
            </div>
            <div className="text-[12px] leading-relaxed text-muted">
              {produto.descricao}
            </div>
            {produto.recursos && produto.recursos.length > 0 && (
              <ul className="list-inside list-disc text-[11px] text-muted">
                {produto.recursos.map((recurso) => (
                  <li key={recurso}>{recurso}</li>
                ))}
              </ul>
            )}
            {produto.conectores && (
              <div className="text-[11px] text-muted">
                {produto.conectores
                  .map(
                    (c) =>
                      `${c.nome} (${ROTULO_DISPONIBILIDADE[c.disponibilidade]})`,
                  )
                  .join(" · ")}
              </div>
            )}
            {produto.incluido_com && (
              <div className="text-[11px] text-cyan">
                Incluído{" "}
                {produto.incluido_com === "plano"
                  ? "nos planos pagos"
                  : `com o ${produto.incluido_com.toUpperCase()}`}
              </div>
            )}
            {(produto.disponibilidade === "SOB_CONSULTA" ||
              produto.disponibilidade === "EM_DEFINICAO") && (
              <a
                href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(`Interesse: ${produto.nome}`)}`}
                className="text-[11px] font-semibold text-cyan hover:underline"
              >
                Quero ser avisado / falar com o comercial →
              </a>
            )}
          </div>
        ))}
      </div>

      {suites.length > 0 && (
        <>
          <div className="mt-14 mb-6 text-center">
            <div className="text-[10px] font-semibold tracking-widest text-cyan uppercase">
              Compare
            </div>
            <div className="mt-1.5 font-head text-xl font-bold text-text">
              Recursos por plano da suíte
            </div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-border bg-surf">
            <table
              className="w-full text-[12px]"
              data-testid="comparativo-planos"
            >
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="p-3 text-muted">Recurso</th>
                  {suites.map((p) => (
                    <th key={p.id} className="p-3 font-head text-text">
                      {p.nome}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border">
                  <td className="p-3 text-muted">Usuários</td>
                  {suites.map((p) => (
                    <td key={p.id} className="p-3 text-text">
                      {formatarLimite(p.max_usuarios)}
                    </td>
                  ))}
                </tr>
                {Object.keys(ROTULO_LIMITE).map((chave) => (
                  <tr key={chave} className="border-b border-border">
                    <td className="p-3 text-muted">{ROTULO_LIMITE[chave]}</td>
                    {suites.map((p) => (
                      <td key={p.id} className="p-3 text-text">
                        {formatarLimite(p.limites[chave])}
                      </td>
                    ))}
                  </tr>
                ))}
                {Object.keys(ROTULO_RECURSO).map((chave) => (
                  <tr
                    key={chave}
                    className="border-b border-border last:border-0"
                  >
                    <td className="p-3 text-muted">{ROTULO_RECURSO[chave]}</td>
                    {suites.map((p) => (
                      <td
                        key={p.id}
                        className={`p-3 ${p.recursos[chave] ? "text-green" : "text-muted"}`}
                      >
                        {p.recursos[chave] ? "✓" : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
