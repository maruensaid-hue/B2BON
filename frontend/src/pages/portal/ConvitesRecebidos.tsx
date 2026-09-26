import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { api, mensagemErro } from "@/lib/api";
import { PortalFornecedor } from "@/pages/portal/PortalFornecedor";

interface Convite {
  participante_id: number;
  comprador: string | null;
  titulo: string;
  tipo_processo: string;
  prazo: string | null;
  situacao: string;
  minha_situacao: string;
}

/** Convites de compra recebidos pela empresa na Business Network (Phase F). */
export function ConvitesRecebidos() {
  const { id } = useParams<{ id: string }>();
  const [convites, setConvites] = useState<Convite[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (id) return;
    api
      .get<Convite[]>("/rede/convites-sourcing")
      .then(setConvites)
      .catch((error) =>
        setErro(mensagemErro(error, "Não foi possível carregar os convites.")),
      );
  }, [id]);

  if (id)
    return (
      <div className="flex flex-col gap-3">
        <Link to="/convites-compra" className="text-[11px] text-cyan">
          ← Convites recebidos
        </Link>
        <PortalFornecedor
          fonte={{ tipo: "rede", participanteId: Number(id) }}
        />
      </div>
    );

  return (
    <div className="flex flex-col gap-3.5" data-testid="convites-recebidos">
      <div className="font-head text-xl font-bold">Convites de compra</div>
      <div className="text-[11px] text-muted">
        Processos de compra em que a sua empresa foi convidada a responder. Você
        vê só o que o comprador compartilhou.
      </div>
      {erro && <div className="text-[12px] text-red">{erro}</div>}
      <Card>
        <SectionLabel>Recebidos</SectionLabel>
        {(convites ?? []).map((c) => (
          <Link
            key={c.participante_id}
            to={`/convites-compra/${c.participante_id}`}
            className="flex items-center justify-between rounded-md border border-border p-2 text-[11px] hover:border-cyan"
          >
            <span>
              <span className="font-semibold text-text">{c.titulo}</span>
              <span className="text-muted">
                {" "}
                · {c.comprador ?? "comprador"} · {c.tipo_processo}
              </span>
            </span>
            <Badge>{c.situacao}</Badge>
          </Link>
        ))}
        {convites?.length === 0 && (
          <div className="text-[11px] text-muted">Nenhum convite.</div>
        )}
      </Card>
    </div>
  );
}
