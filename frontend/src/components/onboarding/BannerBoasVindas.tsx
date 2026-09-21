import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/lib/auth";

interface Atalho {
  emoji: string;
  titulo: string;
  descricao: string;
  href: string;
}

const ATALHOS: Atalho[] = [
  {
    emoji: "🎯",
    titulo: "Crie seu primeiro ICP",
    descricao: "Defina o perfil de cliente ideal pra começar a prospectar.",
    href: "/prospeccao",
  },
  {
    emoji: "🐟",
    titulo: "Publique no Shoal",
    descricao: "Apresente sua empresa pra rede de assinantes da B2B ON.",
    href: "/rede-social",
  },
  {
    emoji: "📦",
    titulo: "Configure sua Oferta",
    descricao: "Cadastre o que você vende pra IA gerar mensagens melhores.",
    href: "/configuracao",
  },
  {
    emoji: "🤝",
    titulo: "Convide um colega",
    descricao: "Traga o resto do time pra dentro da plataforma.",
    href: "/admin/convites",
  },
];

/** Banner de boas-vindas com atalhos rápidos (redesign Salesforce, raio-X
 * 2026-09-21) — coexiste com o `TourGuiado` passo a passo, não o substitui;
 * é só um nudge rápido pras primeiras ações, exibido só na Dashboard.
 * Dispensa em definitivo por usuário (não por tenant — ver `Usuario.
 * boas_vindas_banner_dispensado`). */
export function BannerBoasVindas() {
  const { usuario, dispensarBannerBoasVindas } = useAuth();
  const [dispensando, setDispensando] = useState(false);

  if (!usuario || usuario.boas_vindas_banner_dispensado) return null;

  async function dispensar() {
    setDispensando(true);
    try {
      await dispensarBannerBoasVindas();
    } finally {
      setDispensando(false);
    }
  }

  return (
    <div className="mb-4 rounded-2xl border border-border2 bg-surf p-4.5 shadow-[0_0_20px_rgba(0,194,255,0.06)]">
      <div className="mb-3.5 flex items-start justify-between gap-3">
        <div>
          <div className="font-head text-[15px] font-bold text-text">Bem-vindo(a) à B2B ON</div>
          <div className="mt-0.5 text-[11.5px] text-muted">
            Alguns atalhos pra você começar — o tour completo continua disponível a qualquer momento no
            painel de IA.
          </div>
        </div>
        <button
          type="button"
          onClick={dispensar}
          disabled={dispensando}
          title="Não mostrar de novo"
          className="shrink-0 text-[13px] text-muted hover:text-text"
        >
          ✕
        </button>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        {ATALHOS.map((atalho) => (
          <Link
            key={atalho.href}
            to={atalho.href}
            className="rounded-xl border border-border bg-surf2 p-3 transition-colors hover:border-cyan"
          >
            <div className="text-lg">{atalho.emoji}</div>
            <div className="mt-1.5 text-[12.5px] font-semibold text-text">{atalho.titulo}</div>
            <div className="mt-0.5 text-[11px] text-muted">{atalho.descricao}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
