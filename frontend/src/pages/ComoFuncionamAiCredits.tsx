import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { SecaoAiCredits } from "@/components/SecaoAiCredits";
import { api } from "@/lib/api";

interface Workload {
  codigo: string;
  modulo: string;
  nome: string;
  creditos_base: number;
  creditos_min: number | null;
  creditos_max: number | null;
  requer_aprovacao: boolean;
}

const PERGUNTAS: { pergunta: string; resposta: string }[] = [
  {
    pergunta: "O que é um AI Credit?",
    resposta:
      "É a unidade de consumo das funções de inteligência artificial da B2B ON. Cada operação consome um número fixo de créditos, conforme a complexidade: uma classificação simples consome 1, uma análise de edital consome 50.",
  },
  {
    pergunta: "Os créditos do plano acumulam?",
    resposta:
      "Não. Os créditos incluídos no plano são mensais e vencem no fim do mês. Os créditos comprados valem por 12 meses.",
  },
  {
    pergunta: "Qual crédito é usado primeiro?",
    resposta:
      "O que vence primeiro. Assim, créditos promocionais e os do mês são consumidos antes dos comprados, que duram mais.",
  },
  {
    pergunta: "Vou ser surpreendido por uma operação cara?",
    resposta:
      "Não. Operações maiores, como a análise de um documento longo, mostram o consumo estimado e só rodam depois da sua confirmação.",
  },
  {
    pergunta: "E se a IA falhar?",
    resposta:
      "Se a operação falhar por problema do provedor ou do sistema, os créditos não são cobrados.",
  },
  {
    pergunta: "Como controlo o consumo?",
    resposta:
      "O administrador define limites por mês, por dia, por usuário, por módulo (por exemplo, PREDATOR até 40%) e para a API, e recebe avisos em 80%, 95% e 100% do uso.",
  },
  {
    pergunta: "Posso recarregar automaticamente?",
    resposta:
      "Sim, só com o seu consentimento: quando o saldo ficar abaixo do limite escolhido, criamos o pedido do pacote e avisamos o administrador.",
  },
];

/** Página pública "Como funcionam os AI Credits" (Fase 15). Tabela de
 * consumo e pacotes vêm da API. */
export function ComoFuncionamAiCredits() {
  const [workloads, setWorkloads] = useState<Workload[]>([]);

  useEffect(() => {
    api
      .get<{ workloads: Workload[] }>("/ai-credits/workloads")
      .then((r) => setWorkloads(r.workloads.filter((w) => w.creditos_base > 0)))
      .catch(() => setWorkloads([]));
  }, []);

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border px-5 py-4">
        <Link to="/planos" className="font-head text-[15px] font-bold">
          B2B ON
        </Link>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-10">
        <h1 className="font-head text-2xl font-bold">
          Como funcionam os AI Credits
        </h1>
        <p className="mt-2 max-w-3xl text-[13px] text-muted">
          Uma carteira de créditos por empresa, compartilhada por todos os
          usuários e módulos. Os créditos vêm do seu plano todo mês e de pacotes
          adicionais. O consumo aparece por módulo, operação, agente e usuário.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {PERGUNTAS.map((item) => (
            <div
              key={item.pergunta}
              className="rounded-xl border border-border bg-surf p-4"
            >
              <div className="text-[13px] font-bold">{item.pergunta}</div>
              <div className="mt-1 text-[12.5px] text-muted">
                {item.resposta}
              </div>
            </div>
          ))}
        </div>

        <h2 className="mt-10 font-head text-lg font-bold">
          Quanto cada operação consome
        </h2>
        <div className="mt-3 overflow-x-auto rounded-xl border border-border">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border text-[10px] tracking-wide text-muted uppercase">
                <th className="p-2 text-left">Operação</th>
                <th className="p-2 text-left">Módulo</th>
                <th className="p-2 text-right">Créditos</th>
              </tr>
            </thead>
            <tbody>
              {workloads.map((w) => (
                <tr key={w.codigo} className="border-b border-border">
                  <td className="p-2">{w.nome}</td>
                  <td className="p-2 text-muted">{w.modulo}</td>
                  <td className="p-2 text-right">
                    {w.creditos_min !== null &&
                    w.creditos_max !== null &&
                    w.creditos_min !== w.creditos_max
                      ? `${w.creditos_min}–${w.creditos_max}`
                      : w.creditos_base}
                    {w.requer_aprovacao && (
                      <span className="text-muted"> · pede confirmação</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SecaoAiCredits comLinkExplicacao={false} />
      </main>
    </div>
  );
}
