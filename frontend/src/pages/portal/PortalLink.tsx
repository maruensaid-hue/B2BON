import { PortalFornecedor } from "@/pages/portal/PortalFornecedor";

/** Página pública do convite (Phase F): o segredo vem no fragmento da URL (`#…`), que o navegador não envia a servidor nenhum. */
export function PortalLink() {
  const token = window.location.hash.replace(/^#/, "");
  return (
    <div className="mx-auto max-w-3xl p-4">
      <div className="mb-3 text-[11px] text-muted">
        B2B ON · resposta a convite de compra
      </div>
      {token ? (
        <PortalFornecedor fonte={{ tipo: "link", token }} />
      ) : (
        <div className="text-[12px] text-muted">
          Link de convite incompleto.
        </div>
      )}
    </div>
  );
}
