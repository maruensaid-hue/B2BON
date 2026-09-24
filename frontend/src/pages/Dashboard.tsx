import { useEffect, useState, type ReactNode } from "react";

import { EditarDashboardModal, type PreferenciaDashboardItem } from "@/components/dashboard/EditarDashboardModal";
import { EconomiaSecao, FunilSecao, KpisNorteSecao, usePainelDesempenho } from "@/components/dashboard/PainelDesempenho";
import { BannerBoasVindas } from "@/components/onboarding/BannerBoasVindas";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

const PREFERENCIAS_DASHBOARD_PADRAO: PreferenciaDashboardItem[] = [
  { chave: "kpis_norte", visivel: true },
  { chave: "funil", visivel: true },
  { chave: "economia", visivel: true },
];

export function Dashboard() {
  const { metricaNorte, funil, economia, erro } = usePainelDesempenho();
  const [preferencias, setPreferencias] = useState<PreferenciaDashboardItem[]>(PREFERENCIAS_DASHBOARD_PADRAO);
  const [modalEditarAberto, setModalEditarAberto] = useState(false);

  useEffect(() => {
    api
      .get<PreferenciaDashboardItem[]>("/painel/preferencias-dashboard")
      .then(setPreferencias)
      .catch(() => undefined);
  }, []);

  const secoes: Record<string, ReactNode> = {
    kpis_norte: <KpisNorteSecao key="kpis_norte" metricaNorte={metricaNorte} economia={economia} />,
    funil: <FunilSecao key="funil" funil={funil} />,
    economia: <EconomiaSecao key="economia" economia={economia} />,
  };

  const secoesVisiveis = preferencias.filter((item) => item.visivel);

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <div className="font-head text-xl font-bold">Dashboard</div>
          <div className="mt-0.5 text-[11px] text-muted">Visão geral · CRM + MAP</div>
        </div>
        <Button size="sm" onClick={() => setModalEditarAberto(true)}>
          ⚙ Editar Dashboard
        </Button>
      </div>

      <BannerBoasVindas />

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      {secoesVisiveis.length === 0 ? (
        <Card className="text-center text-[12.5px] text-muted">
          Todas as seções da Dashboard estão ocultas.{" "}
          <button type="button" className="text-cyan hover:underline" onClick={() => setModalEditarAberto(true)}>
            Editar Dashboard
          </button>{" "}
          pra mostrar alguma de novo.
        </Card>
      ) : (
        secoesVisiveis.map((item) => secoes[item.chave])
      )}

      <EditarDashboardModal
        open={modalEditarAberto}
        onClose={() => setModalEditarAberto(false)}
        itens={preferencias}
        onSalvo={setPreferencias}
      />
    </div>
  );
}
