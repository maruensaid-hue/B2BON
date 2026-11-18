import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { Select } from "@/components/ui/Input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatarData, formatarMoeda } from "@/lib/inadimplencia";

interface Opcao {
  id: string | number;
  nome: string;
}

interface Opcoes {
  tenants: Opcao[];
  vendedores: Opcao[];
  representantes: Opcao[];
  revendas: Opcao[];
  distribuidores: Opcao[];
}

interface Resumo {
  total_em_atraso: number;
  quantidade: number;
  clientes: number;
  maior_atraso_dias: number;
}

interface ColunasRede {
  tenant_id: string;
  tenant_nome: string;
  representante_nome: string | null;
  revenda_nome: string | null;
  distribuidor_nome: string | null;
  cliente: string;
  dias_atraso: number;
  vencimento: string;
}

interface LinhaParcela extends ColunasRede {
  parcela_id: number;
  negocio_id: number;
  negocio_nome: string;
  vendedor_nome: string | null;
  numero: number;
  valor: number;
}

interface LinhaLicenca extends ColunasRede {
  licenca_id: number;
  plano_nome: string;
  valor_mensal: number;
  situacao: "em_carencia" | "pagamento_declarado" | "vencida" | "suspensa";
}

interface Quadro<T> {
  resumo: Resumo;
  linhas: T[];
  opcoes: Opcoes;
}

interface Filtros {
  tenant_id_selecionado: string;
  vendedor_usuario_id: string;
  representante_id: string;
  revenda_id: string;
  distribuidor_id: string;
}

const FILTROS_VAZIOS: Filtros = { tenant_id_selecionado: "", vendedor_usuario_id: "", representante_id: "", revenda_id: "", distribuidor_id: "" };

const SITUACAO: Record<LinhaLicenca["situacao"], { rotulo: string; tom: "amber" | "red" | "violet" }> = {
  em_carencia: { rotulo: "Em carência", tom: "amber" },
  pagamento_declarado: { rotulo: "Diz que pagou", tom: "violet" },
  vencida: { rotulo: "Vencida", tom: "red" },
  suspensa: { rotulo: "Suspensa", tom: "red" },
};

function consulta(filtros: Filtros, campos: (keyof Filtros)[]): string {
  const params = new URLSearchParams();
  for (const campo of campos) if (filtros[campo]) params.set(campo, filtros[campo]);
  const texto = params.toString();
  return texto ? `?${texto}` : "";
}

function SeletorFiltro({ rotulo, valor, opcoes, aoMudar }: { rotulo: string; valor: string; opcoes: Opcao[]; aoMudar: (v: string) => void }) {
  if (opcoes.length < 2 && !valor) return null;
  return (
    <div className="min-w-[150px] flex-1">
      <Select label={rotulo} value={valor} onChange={(e) => aoMudar(e.target.value)}>
        <option value="">Todos</option>
        {opcoes.map((opcao) => (
          <option key={String(opcao.id)} value={String(opcao.id)}>{opcao.nome}</option>
        ))}
      </Select>
    </div>
  );
}

function Resumos({ resumo, rotuloValor }: { resumo: Resumo; rotuloValor: string }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
      <KpiCard label={rotuloValor} value={formatarMoeda(resumo.total_em_atraso)} colorClassName="text-red" />
      <KpiCard label="Clientes" value={resumo.clientes} colorClassName="text-amber" />
      <KpiCard label="Em atraso" value={resumo.quantidade} />
      <KpiCard label="Maior atraso" value={`${resumo.maior_atraso_dias} d`} colorClassName="text-red" />
    </div>
  );
}

function Rede({ linha, mostrarTenant }: { linha: ColunasRede; mostrarTenant: boolean }) {
  const partes = [
    mostrarTenant ? linha.tenant_nome : null,
    linha.revenda_nome && linha.revenda_nome !== linha.tenant_nome ? `Revenda: ${linha.revenda_nome}` : null,
    linha.distribuidor_nome && linha.distribuidor_nome !== linha.tenant_nome ? `Distribuidor: ${linha.distribuidor_nome}` : null,
    linha.representante_nome ? `Representante: ${linha.representante_nome}` : null,
  ].filter(Boolean);
  return <span className="text-[11px] text-muted">{partes.join(" · ") || "—"}</span>;
}

/** Quadro "Clientes inadimplentes" do MAP (pedido do PO, 18/11/2026). Duas seções:
 * - Parcelas: pagamentos combinados nos negócios ganhos (lançados pelo vendedor no CRM) que venceram sem pagamento. Vendedor vê os dele; gestor vê o
 *   tenant e, se for distribuidor/revenda ou super_admin, a rede abaixo dele.
 * - Licenças: tenants com a licença da B2B ON vencida sem pagamento confirmado — para a gestão da B2B ON, distribuidores, revendas e representantes.
 * Os filtros só oferecem o que a pessoa já pode ver (a regra de visibilidade fica no backend). */
export function MapInadimplentes({ verParcelas, verLicencas }: { verParcelas: boolean; verLicencas: boolean }) {
  const { usuario } = useAuth();
  const [secao, setSecao] = useState<"parcelas" | "licencas">(verParcelas ? "parcelas" : "licencas");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VAZIOS);
  const [parcelas, setParcelas] = useState<Quadro<LinhaParcela> | null>(null);
  const [licencas, setLicencas] = useState<Quadro<LinhaLicenca> | null>(null);
  const [opcoesBase, setOpcoesBase] = useState<Opcoes | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const ehVendedor = usuario?.papel === "user";

  useEffect(() => {
    setFiltros(FILTROS_VAZIOS);
    setOpcoesBase(null);
  }, [secao]);

  useEffect(() => {
    setErro(null);
    if (secao === "parcelas") {
      api
        .get<Quadro<LinhaParcela>>(`/map/inadimplencia/parcelas${consulta(filtros, ["tenant_id_selecionado", "vendedor_usuario_id", "representante_id", "revenda_id", "distribuidor_id"])}`)
        .then((q) => {
          setParcelas(q);
          setOpcoesBase((atual) => atual ?? q.opcoes);
        })
        .catch((error) => setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as parcelas em atraso."));
    } else {
      api
        .get<Quadro<LinhaLicenca>>(`/map/inadimplencia/licencas${consulta(filtros, ["tenant_id_selecionado", "representante_id", "revenda_id", "distribuidor_id"])}`)
        .then((q) => {
          setLicencas(q);
          setOpcoesBase((atual) => atual ?? q.opcoes);
        })
        .catch((error) => setErro(error instanceof ApiError ? error.message : "Não foi possível carregar as licenças vencidas."));
    }
  }, [secao, filtros]);

  function mudar(campo: keyof Filtros, valor: string) {
    setFiltros((atual) => ({ ...atual, [campo]: valor }));
  }

  const opcoes = opcoesBase;
  const mostrarTenant = (opcoes?.tenants.length ?? 0) > 1;

  return (
    <div className="space-y-3 p-5.5">
      <div>
        <div className="font-head text-xl font-bold">Clientes inadimplentes</div>
        <div className="mt-0.5 text-[11px] text-muted">
          {secao === "parcelas"
            ? "Parcelas combinadas nos negócios ganhos que passaram do vencimento sem pagamento. Lance e dê baixa nas parcelas dentro do negócio, no CRM."
            : "Tenants com a licença da B2B ON vencida e sem pagamento confirmado (carência de 3 dias antes da suspensão)."}
        </div>
      </div>

      {verParcelas && verLicencas && (
        <div className="flex gap-2">
          {([["parcelas", "Parcelas dos clientes"], ["licencas", "Licenças B2B ON"]] as const).map(([chave, rotulo]) => (
            <button key={chave} type="button" onClick={() => setSecao(chave)}
              className={`rounded-lg border px-3 py-1.5 text-[12px] ${secao === chave ? "border-cyan text-cyan" : "border-border text-muted"}`}>
              {rotulo}
            </button>
          ))}
        </div>
      )}

      {opcoes && (
        <div className="flex flex-wrap gap-2">
          <SeletorFiltro rotulo="Tenant" valor={filtros.tenant_id_selecionado} opcoes={opcoes.tenants} aoMudar={(v) => mudar("tenant_id_selecionado", v)} />
          {secao === "parcelas" && !ehVendedor && (
            <SeletorFiltro rotulo="Vendedor" valor={filtros.vendedor_usuario_id} opcoes={opcoes.vendedores} aoMudar={(v) => mudar("vendedor_usuario_id", v)} />
          )}
          <SeletorFiltro rotulo="Representante" valor={filtros.representante_id} opcoes={opcoes.representantes} aoMudar={(v) => mudar("representante_id", v)} />
          <SeletorFiltro rotulo="Revenda" valor={filtros.revenda_id} opcoes={opcoes.revendas} aoMudar={(v) => mudar("revenda_id", v)} />
          <SeletorFiltro rotulo="Distribuidor" valor={filtros.distribuidor_id} opcoes={opcoes.distribuidores} aoMudar={(v) => mudar("distribuidor_id", v)} />
        </div>
      )}

      {erro && <Card className="p-3 text-[12px] text-red">{erro}</Card>}

      {secao === "parcelas" && parcelas && (
        <>
          <Resumos resumo={parcelas.resumo} rotuloValor="Total em atraso" />
          <Card className="p-4">
            <SectionLabel>Parcelas vencidas sem pagamento</SectionLabel>
            {parcelas.linhas.length === 0 ? (
              <div className="text-[12px] text-muted">Nenhuma parcela em atraso. 🎉</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-left text-[10px] tracking-wide text-muted uppercase">
                      <th className="py-1.5 pr-2">Cliente</th>
                      <th className="py-1.5 pr-2">Parcela</th>
                      <th className="py-1.5 pr-2">Valor</th>
                      <th className="py-1.5 pr-2">Vencimento</th>
                      <th className="py-1.5 pr-2">Atraso</th>
                      <th className="py-1.5 pr-2">Vendedor</th>
                      <th className="py-1.5">Rede</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parcelas.linhas.map((linha) => (
                      <tr key={linha.parcela_id} className="border-t border-border align-top">
                        <td className="py-1.5 pr-2">
                          <div className="font-bold">{linha.cliente}</div>
                          {linha.tenant_id === usuario?.tenant_id ? (
                            <Link to={`/crm/negocios/${linha.negocio_id}`} className="text-[11px] text-cyan hover:underline">{linha.negocio_nome}</Link>
                          ) : (
                            <div className="text-[11px] text-muted">{linha.negocio_nome}</div>
                          )}
                        </td>
                        <td className="py-1.5 pr-2">{linha.numero}ª</td>
                        <td className="py-1.5 pr-2">{formatarMoeda(linha.valor)}</td>
                        <td className="py-1.5 pr-2">{formatarData(linha.vencimento)}</td>
                        <td className="py-1.5 pr-2"><Badge tone={linha.dias_atraso > 30 ? "red" : "amber"}>{linha.dias_atraso} d</Badge></td>
                        <td className="py-1.5 pr-2">{linha.vendedor_nome ?? <span className="text-muted">Sem vendedor</span>}</td>
                        <td className="py-1.5"><Rede linha={linha} mostrarTenant={mostrarTenant} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {secao === "licencas" && licencas && (
        <>
          <Resumos resumo={licencas.resumo} rotuloValor="Mensalidades em atraso" />
          <Card className="p-4">
            <SectionLabel>Licenças vencidas sem pagamento confirmado</SectionLabel>
            {licencas.linhas.length === 0 ? (
              <div className="text-[12px] text-muted">Nenhuma licença vencida. 🎉</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-left text-[10px] tracking-wide text-muted uppercase">
                      <th className="py-1.5 pr-2">Cliente (tenant)</th>
                      <th className="py-1.5 pr-2">Plano</th>
                      <th className="py-1.5 pr-2">Mensalidade</th>
                      <th className="py-1.5 pr-2">Vencimento</th>
                      <th className="py-1.5 pr-2">Atraso</th>
                      <th className="py-1.5 pr-2">Situação</th>
                      <th className="py-1.5">Rede</th>
                    </tr>
                  </thead>
                  <tbody>
                    {licencas.linhas.map((linha) => (
                      <tr key={linha.licenca_id} className="border-t border-border align-top">
                        <td className="py-1.5 pr-2 font-bold">{linha.cliente}</td>
                        <td className="py-1.5 pr-2">{linha.plano_nome}</td>
                        <td className="py-1.5 pr-2">{formatarMoeda(linha.valor_mensal)}</td>
                        <td className="py-1.5 pr-2">{formatarData(linha.vencimento)}</td>
                        <td className="py-1.5 pr-2">{linha.dias_atraso} d</td>
                        <td className="py-1.5 pr-2"><Badge tone={SITUACAO[linha.situacao].tom}>{SITUACAO[linha.situacao].rotulo}</Badge></td>
                        <td className="py-1.5"><Rede linha={linha} mostrarTenant={false} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
