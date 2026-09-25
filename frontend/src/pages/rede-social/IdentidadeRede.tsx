import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface EmpresaRede {
  id: number;
  tenant_id: string | null;
  cnpj: string | null;
  nome_exibicao: string;
  status: "NAO_REIVINDICADA" | "REIVINDICADA" | "VERIFICADA" | "MESCLADA";
}

const ROTULO_STATUS: Record<
  EmpresaRede["status"],
  { texto: string; tom: "green" | "cyan" | "muted" | "amber" }
> = {
  VERIFICADA: { texto: "Identidade verificada", tom: "green" },
  REIVINDICADA: { texto: "Identidade não verificada", tom: "amber" },
  NAO_REIVINDICADA: { texto: "Não reivindicada", tom: "muted" },
  MESCLADA: { texto: "Mesclada", tom: "muted" },
};

const TIPOS_RELACIONAMENTO: Record<string, string> = {
  CUSTOMER_OF: "Somos clientes de",
  SUPPLIER_OF: "Somos fornecedores de",
  PARTNER_OF: "Somos parceiros de",
  RESELLER_OF: "Somos revendedores de",
  DISTRIBUTOR_OF: "Somos distribuidores de",
  INTEGRATES_WITH: "Integramos com",
  USES_TECHNOLOGY: "Usamos a tecnologia de",
};

/** Business Network Foundation (Fase 7): identidade da empresa na rede,
 * reivindicação de identidades citadas por outras empresas com o mesmo
 * CNPJ, visibilidade no diretório e relacionamento com empresa que ainda
 * não está na rede. Ações de identidade são só de administradores. */
export function IdentidadeRede({
  visivelNoDiretorio,
  aoAlterar,
}: {
  visivelNoDiretorio: boolean;
  aoAlterar: () => void;
}) {
  const { usuario } = useAuth();
  const admin = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const [empresa, setEmpresa] = useState<EmpresaRede | null>(null);
  const [reivindicaveis, setReivindicaveis] = useState<EmpresaRede[]>([]);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const resposta = await api.get<{
        empresa: EmpresaRede;
        reivindicaveis: EmpresaRede[];
      }>("/rede-social/identidade");
      setEmpresa(resposta.empresa);
      setReivindicaveis(resposta.reivindicaveis);
    } catch {
      setErro("Não foi possível carregar a identidade da empresa na rede.");
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function executar(acao: () => Promise<unknown>, sucesso: string) {
    setErro(null);
    setMensagem(null);
    try {
      await acao();
      setMensagem(sucesso);
      await carregar();
      aoAlterar();
    } catch (error) {
      setErro(
        error instanceof ApiError
          ? error.message
          : "Não foi possível concluir a ação.",
      );
    }
  }

  function declararPorCnpj(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formulario = event.currentTarget;
    const form = new FormData(formulario);
    executar(async () => {
      await api.post("/rede-social/relacionamentos/por-cnpj", {
        cnpj: String(form.get("cnpj")),
        nome: String(form.get("nome") ?? "") || null,
        tipo: String(form.get("tipo")),
        visibilidade: String(form.get("visibilidade")),
      });
      formulario.reset();
    }, "Relacionamento registrado. Se a empresa ainda não está na rede, ela poderá reivindicar esta identidade.");
  }

  if (!empresa)
    return erro ? (
      <div className="mb-4 text-[11px] text-red">{erro}</div>
    ) : null;

  return (
    <Card className="mb-4" data-testid="identidade-rede">
      <div className="flex items-center justify-between">
        <SectionLabel>Identidade da empresa na rede</SectionLabel>
        <Badge tone={ROTULO_STATUS[empresa.status].tom}>
          {ROTULO_STATUS[empresa.status].texto}
        </Badge>
      </div>
      <div className="text-[11px] text-muted">
        {empresa.nome_exibicao}
        {empresa.cnpj ? ` · CNPJ ${empresa.cnpj}` : " · CNPJ não cadastrado"}
      </div>
      {erro && <div className="mt-2 text-[11px] text-red">{erro}</div>}
      {mensagem && (
        <div className="mt-2 text-[11px] text-green">{mensagem}</div>
      )}

      {reivindicaveis.length > 0 && (
        <div className="mt-3 rounded-md border border-border p-2 text-[11px]">
          <div className="text-text">
            Outras empresas citaram o seu CNPJ na rede:
          </div>
          {reivindicaveis.map((item) => (
            <div
              key={item.id}
              className="mt-1 flex items-center justify-between gap-2"
            >
              <span className="text-muted">{item.nome_exibicao}</span>
              {admin && (
                <Button
                  size="sm"
                  onClick={() =>
                    executar(
                      () =>
                        api.post(
                          `/rede-social/identidades/${item.id}/reivindicar`,
                        ),
                      "Identidade reivindicada.",
                    )
                  }
                >
                  Reivindicar
                </Button>
              )}
            </div>
          ))}
          {empresa.status !== "VERIFICADA" && (
            <div className="mt-1 text-[10px] text-muted">
              Para reivindicar, a empresa precisa estar verificada.
            </div>
          )}
        </div>
      )}

      {admin && (
        <>
          <label className="mt-3 flex items-center gap-2 text-[11px] text-muted">
            <input
              type="checkbox"
              checked={visivelNoDiretorio}
              onChange={(event) =>
                executar(
                  () =>
                    api.put("/rede-social/perfil/visibilidade", {
                      visivel_no_diretorio: event.target.checked,
                    }),
                  event.target.checked
                    ? "Empresa visível no diretório."
                    : "Empresa oculta do diretório (conexões continuam vendo).",
                )
              }
            />
            Aparecer no diretório da rede para empresas que ainda não são
            conexões
          </label>

          <form onSubmit={declararPorCnpj} className="mt-3 flex flex-col gap-2">
            <div className="text-[10px] tracking-wide text-muted uppercase">
              Relacionamento com empresa que ainda não está na rede
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
              <Select name="tipo" defaultValue="CUSTOMER_OF">
                {Object.entries(TIPOS_RELACIONAMENTO).map(([valor, rotulo]) => (
                  <option key={valor} value={valor}>
                    {rotulo}
                  </option>
                ))}
              </Select>
              <Input name="cnpj" required placeholder="CNPJ" />
              <Input name="nome" placeholder="Nome da empresa" />
              <Select name="visibilidade" defaultValue="publica">
                <option value="publica">Pública</option>
                <option value="conexoes">Só conexões</option>
                <option value="privada">Privada (só nós)</option>
              </Select>
            </div>
            <Button type="submit" size="sm" className="self-start">
              Registrar relacionamento
            </Button>
          </form>
        </>
      )}
    </Card>
  );
}
