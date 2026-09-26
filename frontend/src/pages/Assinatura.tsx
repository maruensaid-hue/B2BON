import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { brl } from "@/lib/aiCredits";
import { api, ApiError } from "@/lib/api";
import {
  formatarLimite,
  ROTULO_DISPONIBILIDADE,
  TOM_DISPONIBILIDADE,
  type Disponibilidade,
} from "@/lib/catalogo";

interface Uso {
  usado: number;
  limite: number | null;
  percentual: number | null;
}

interface AssinaturaResposta {
  plano: {
    nome: string;
    categoria: string;
    preco_mensal: number;
    tipo_preco: "FIXED" | "STARTING_AT";
  } | null;
  licenca: { status: string; expira_em: string | null };
  modulos: {
    id: string;
    nome: string;
    modulo: string;
    disponibilidade: Disponibilidade;
    contratado: boolean;
  }[];
  uso: {
    periodo: string;
    usuarios: Uso;
    franquia_contas: Uso;
    cadencias: Uso;
    campanhas: Uso;
  };
  ia: {
    chamadas_no_mes: number;
    creditos_consumidos: number | null;
    saldo_creditos: number;
    franquia_mensal: number;
  };
  conectores: {
    sistema: string;
    nome: string;
    disponibilidade: Disponibilidade;
    liberado_para_conexao: boolean;
  }[];
}

const ROTULO_USO: Record<
  keyof Omit<AssinaturaResposta["uso"], "periodo">,
  string
> = {
  usuarios: "Usuários ativos",
  franquia_contas: "Contas ativadas (franquia PREDATOR)",
  cadencias: "Cadências criadas no mês",
  campanhas: "Campanhas criadas no mês",
};

function BarraUso({ rotulo, uso }: { rotulo: string; uso: Uso }) {
  const percentual = uso.percentual ?? 0;
  return (
    <div className="flex flex-col gap-1 text-[12px]">
      <div className="flex justify-between">
        <span className="text-muted">{rotulo}</span>
        <span className="font-semibold text-text">
          {uso.usado.toLocaleString("pt-BR")} / {formatarLimite(uso.limite)}
        </span>
      </div>
      {uso.limite ? (
        <div className="h-1.5 rounded-full bg-surf2">
          <div
            className={`h-1.5 rounded-full ${percentual >= 90 ? "bg-red" : percentual >= 70 ? "bg-amber" : "bg-cyan"}`}
            style={{ width: `${Math.min(percentual, 100)}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Assinatura do tenant (Fase 14): plano, módulos contratados e
 * disponíveis, uso do mês e consumo de IA. Preço exibido é o do plano
 * no banco (o mesmo que o checkout cobra). */
export function Assinatura() {
  const [dados, setDados] = useState<AssinaturaResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AssinaturaResposta>("/assinatura")
      .then(setDados)
      .catch((error) =>
        setErro(
          error instanceof ApiError
            ? error.message
            : "Não foi possível carregar a assinatura.",
        ),
      );
  }, []);

  if (!dados)
    return (
      <div className="text-[12px] text-muted">{erro ?? "Carregando..."}</div>
    );

  return (
    <div className="flex flex-col gap-4" data-testid="assinatura">
      <div>
        <div className="font-head text-xl font-bold">Assinatura</div>
        <div className="text-[11px] text-muted">
          Plano, módulos e uso de {dados.uso.periodo}.
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-3">
        <Card>
          <SectionLabel>Plano atual</SectionLabel>
          {dados.plano ? (
            <div className="flex flex-col gap-1 text-[12px]">
              <div className="font-head text-lg font-bold text-text">
                {dados.plano.nome}
              </div>
              <div className="text-muted">
                {dados.plano.tipo_preco === "STARTING_AT"
                  ? `Condições por contrato (a partir de ${brl(dados.plano.preco_mensal)} / mês)`
                  : dados.plano.preco_mensal > 0
                    ? `${brl(dados.plano.preco_mensal)} / mês`
                    : "Sem cobrança"}
              </div>
              <div>
                Licença{" "}
                <Badge
                  tone={dados.licenca.status === "ativa" ? "green" : "red"}
                >
                  {dados.licenca.status}
                </Badge>
              </div>
              {dados.licenca.expira_em && (
                <div className="text-muted">
                  Vence em{" "}
                  {new Date(dados.licenca.expira_em).toLocaleDateString(
                    "pt-BR",
                  )}
                </div>
              )}
              <Link
                to="/planos"
                className="mt-1 text-[11px] font-semibold text-cyan hover:underline"
              >
                Ver planos e valores →
              </Link>
            </div>
          ) : (
            <div className="text-[12px] text-muted">
              Sem licença. Veja os planos para contratar.
            </div>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Uso do mês</SectionLabel>
          <div className="flex flex-col gap-2.5">
            {(Object.keys(ROTULO_USO) as (keyof typeof ROTULO_USO)[]).map(
              (chave) => (
                <BarraUso
                  key={chave}
                  rotulo={ROTULO_USO[chave]}
                  uso={dados.uso[chave]}
                />
              ),
            )}
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <SectionLabel>Módulos</SectionLabel>
          <div className="flex flex-col gap-1.5 text-[12px]">
            {dados.modulos.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between gap-2"
              >
                <span className="text-text">{m.nome}</span>
                {m.contratado ? (
                  <Badge tone="green">Contratado</Badge>
                ) : (
                  <span className="flex items-center gap-2">
                    <Badge tone={TOM_DISPONIBILIDADE[m.disponibilidade]}>
                      {ROTULO_DISPONIBILIDADE[m.disponibilidade]}
                    </Badge>
                    {m.disponibilidade === "DISPONIVEL" ? (
                      <Link
                        to="/planos"
                        className="text-[11px] font-semibold text-cyan hover:underline"
                      >
                        Contratar
                      </Link>
                    ) : (
                      <a
                        href={`mailto:comercial@cyberfort.com.br?subject=${encodeURIComponent(`Interesse: ${m.nome}`)}`}
                        className="text-[11px] font-semibold text-cyan hover:underline"
                      >
                        Falar com o comercial
                      </a>
                    )}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionLabel>IA no mês</SectionLabel>
          <div className="flex flex-col gap-1 text-[12px]">
            <div className="flex justify-between">
              <span className="text-muted">Chamadas de IA</span>
              <span className="font-semibold text-text">
                {dados.ia.chamadas_no_mes.toLocaleString("pt-BR")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">AI Credits consumidos</span>
              <span className="font-semibold text-text">
                {(dados.ia.creditos_consumidos ?? 0).toLocaleString("pt-BR")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">AI Credits disponíveis</span>
              <span className="font-semibold text-text">
                {dados.ia.saldo_creditos.toLocaleString("pt-BR")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Incluídos no plano (mês)</span>
              <span className="font-semibold text-text">
                {dados.ia.franquia_mensal.toLocaleString("pt-BR")}
              </span>
            </div>
            <Link
              to="/ai-credits"
              className="mt-1 text-[11px] font-semibold text-cyan hover:underline"
            >
              Ver carteira e comprar AI Credits
            </Link>
          </div>
        </Card>

        <Card className="lg:col-span-3">
          <SectionLabel>Conectores de CRM</SectionLabel>
          <div className="flex flex-wrap gap-2 text-[12px]">
            {dados.conectores.map((c) => (
              <span key={c.sistema} className="flex items-center gap-1.5">
                {c.nome}
                <Badge
                  tone={
                    c.liberado_para_conexao
                      ? "green"
                      : TOM_DISPONIBILIDADE[c.disponibilidade]
                  }
                >
                  {c.liberado_para_conexao
                    ? "Liberado"
                    : ROTULO_DISPONIBILIDADE[c.disponibilidade]}
                </Badge>
              </span>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
