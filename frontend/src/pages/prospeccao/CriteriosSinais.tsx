import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { api } from "@/lib/api";

export interface CriterioSinal {
  codigo: string;
  regra: "exigir" | "excluir" | "faixa";
  minimo?: number | null;
  maximo?: number | null;
  valor?: string;
}

interface SinalCatalogo {
  codigo: string;
  rotulo: string;
  tipo: "bool" | "num" | "texto";
  descricao: string;
}

interface Coorte {
  total: number;
  avaliadas: number;
}

const ROTULO_REGRA: Record<CriterioSinal["regra"], string> = { exigir: "precisa ter", excluir: "não pode ter", faixa: "entre" };

function regrasDoTipo(tipo: SinalCatalogo["tipo"] | undefined): CriterioSinal["regra"][] {
  return tipo === "num" ? ["faixa"] : ["exigir", "excluir"];
}

/** Critérios de sinais do ICP: a lista vira uma consulta, e a contagem de contas que já atendem aparece enquanto se monta. */
export function CriteriosSinais({ inicial, icpId }: { inicial: CriterioSinal[]; icpId: number | null }) {
  const [catalogo, setCatalogo] = useState<SinalCatalogo[]>([]);
  const [criterios, setCriterios] = useState<CriterioSinal[]>(inicial);
  const [coorte, setCoorte] = useState<Coorte | null>(null);
  const [erroCoorte, setErroCoorte] = useState<string | null>(null);

  useEffect(() => {
    api.get<SinalCatalogo[]>("/icp/sinais/catalogo").then(setCatalogo).catch(() => setCatalogo([]));
  }, []);

  const completos = criterios.filter(
    (c) => c.codigo && (c.regra !== "faixa" || c.minimo != null || c.maximo != null) && (tipoDe(c.codigo) !== "texto" || c.valor),
  );

  useEffect(() => {
    if (completos.length === 0) {
      setCoorte(null);
      return;
    }
    const temporizador = setTimeout(() => {
      api
        .post<Coorte>("/icp/coorte", { criterios: completos, icp_id: icpId, limite: 1 })
        .then((resultado) => {
          setCoorte(resultado);
          setErroCoorte(null);
        })
        .catch(() => setErroCoorte("Não foi possível contar as contas agora."));
    }, 400);
    return () => clearTimeout(temporizador);
  }, [JSON.stringify(completos), icpId]);

  function tipoDe(codigo: string) {
    return catalogo.find((s) => s.codigo === codigo)?.tipo;
  }

  function atualizar(indice: number, mudanca: Partial<CriterioSinal>) {
    setCriterios((atuais) => atuais.map((c, i) => (i === indice ? { ...c, ...mudanca } : c)));
  }

  function trocarSinal(indice: number, codigo: string) {
    const regra = regrasDoTipo(tipoDe(codigo))[0];
    atualizar(indice, { codigo, regra, minimo: null, maximo: null, valor: "" });
  }

  const numero = (texto: string) => (texto.trim() === "" ? null : Number(texto.replace(",", ".")));

  return (
    <div>
      <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Sinais das contas (opcional)</div>
      <input type="hidden" name="criterios_sinais" value={JSON.stringify(completos)} />
      <div className="flex flex-col gap-1.5">
        {criterios.map((criterio, indice) => {
          const tipo = tipoDe(criterio.codigo);
          return (
            <div key={indice} className="flex flex-wrap items-center gap-1.5">
              <Select value={criterio.codigo} onChange={(e) => trocarSinal(indice, e.target.value)} aria-label="Sinal">
                <option value="">Escolha um sinal</option>
                {catalogo.map((s) => (
                  <option key={s.codigo} value={s.codigo} title={s.descricao}>
                    {s.rotulo}
                  </option>
                ))}
              </Select>
              <Select
                value={criterio.regra}
                onChange={(e) => atualizar(indice, { regra: e.target.value as CriterioSinal["regra"] })}
                aria-label="Regra"
              >
                {regrasDoTipo(tipo).map((regra) => (
                  <option key={regra} value={regra}>
                    {ROTULO_REGRA[regra]}
                  </option>
                ))}
              </Select>
              {criterio.regra === "faixa" && (
                <>
                  <Input className="w-20" placeholder="mín." defaultValue={criterio.minimo ?? ""} onChange={(e) => atualizar(indice, { minimo: numero(e.target.value) })} />
                  <Input className="w-20" placeholder="máx." defaultValue={criterio.maximo ?? ""} onChange={(e) => atualizar(indice, { maximo: numero(e.target.value) })} />
                </>
              )}
              {tipo === "texto" && (
                <Input className="w-40" placeholder="valor exato" defaultValue={criterio.valor ?? ""} onChange={(e) => atualizar(indice, { valor: e.target.value })} />
              )}
              <Button size="sm" type="button" onClick={() => setCriterios((atuais) => atuais.filter((_, i) => i !== indice))}>
                Remover
              </Button>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <Button size="sm" type="button" onClick={() => setCriterios((atuais) => [...atuais, { codigo: "", regra: "exigir" }])}>
          Adicionar sinal
        </Button>
        {coorte && (
          <span className="text-[11px] text-muted">
            {coorte.total} de {coorte.avaliadas} conta(s) {icpId ? "deste ICP " : ""}já atendem
          </span>
        )}
        {erroCoorte && <span className="text-[11px] text-muted">{erroCoorte}</span>}
      </div>
      <div className="mt-1 text-[11px] text-muted/70">
        Sinais são coletados sem custo no enriquecimento de cada conta (site e cadastro público). Conta ainda não enriquecida não atende.
      </div>
    </div>
  );
}
