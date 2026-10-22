import { Fragment, useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { KpiCard } from "@/components/ui/KpiCard";
import { api, getBlob, mensagemErro } from "@/lib/api";

interface UsuarioIa {
  usuario_id: number | null;
  nome: string;
  email: string | null;
  papel: string | null;
  creditos: number;
  execucoes: number;
  excedente: number;
}
interface UsuarioContatos {
  usuario_id: number | null;
  nome: string;
  email: string | null;
  papel: string | null;
  creditos: number;
  pesquisas: number;
  empresas: number;
  decisores: number;
}
interface Aquisicao {
  produto: "IA" | "Decisores";
  pacote: string;
  creditos: number;
  valor_brl: string;
  data: string;
  empresa: string;
  tenant_id: string;
  valido_ate?: string | null;
  origem?: string;
}
interface Ia {
  franquia_mensal: number;
  consumo_total: number;
  consumo_da_franquia: number;
  consumo_adicional: { pacotes_comprados: number; bonus_e_ajustes: number; total: number };
  consumo_excedente: { creditos: number; valor_brl: string };
  uso_da_franquia_percentual: number | null;
  expirado: number;
  saldo_atual: number;
  por_usuario: UsuarioIa[];
}
interface Contatos {
  perfil: { origem: string; modo: string; periodicidade: string | null } | null;
  sem_configuracao: string | null;
  franquia_mensal: number | null;
  limite_por_pesquisa: number | null;
  limite_por_pesquisa_origem: string;
  decisores_por_empresa_max: number | null;
  empresas_por_pesquisa_max: number | null;
  consumo_total: number;
  consumo_da_franquia: number;
  consumo_adicional: { pacotes_comprados: number; outros: number; total: number };
  uso_da_franquia_percentual: number | null;
  expirado: number;
  saldo_atual: number;
  por_usuario: UsuarioContatos[];
}
interface Empresa {
  tenant_id: string;
  empresa: string;
  plano: string | null;
  ia: Ia;
  contatos: Contatos;
}
interface Relatorio {
  periodo: { inicio: string; fim: string };
  totais: {
    empresas: number;
    ia: { consumo_total: number; consumo_da_franquia: number; consumo_adicional: number };
    contatos: { consumo_total: number; consumo_da_franquia: number; consumo_adicional: number };
    aquisicoes: { quantidade: number; creditos: number; valor_brl: string };
  };
  empresas: Empresa[];
  aquisicoes: Aquisicao[];
  notas: string[];
}

const num = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const reais = (v: string) => `R$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dia = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
const ROTULO_PAPEL: Record<string, string> = { super_admin: "Super admin", admin: "Admin", user: "Usuário" };

function primeiroDiaDoMes(): string {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toLocaleDateString("sv-SE");
}

function Uso({ valor }: { valor: number | null }) {
  if (valor === null) return <span className="text-muted">—</span>;
  return <Badge tone={valor >= 100 ? "red" : valor >= 80 ? "amber" : "green"}>{valor}%</Badge>;
}

/** Consumo de créditos de IA e de enriquecimento por empresa e por usuário, com a franquia e os limites do perfil contratado, as aquisições de créditos
 * adicionais (quantidade, data e valor) e o consumo adicional. Super admin vê todas as empresas; admin, a sua (e a subárvore). */
export function RelatorioConsumoCreditos() {
  const [inicio, setInicio] = useState(primeiroDiaDoMes());
  const [fim, setFim] = useState(new Date().toLocaleDateString("sv-SE"));
  const [empresaFiltro, setEmpresaFiltro] = useState("");
  const [dados, setDados] = useState<Relatorio | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const consulta = useCallback(
    (extra: Record<string, string> = {}) => new URLSearchParams({ inicio, fim, ...extra }).toString(),
    [inicio, fim],
  );

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      setDados(await api.get<Relatorio>(`/relatorio-consumo-creditos?${consulta()}`));
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível gerar o relatório."));
    } finally {
      setCarregando(false);
    }
  }, [consulta]);

  useEffect(() => {
    void carregar();
    // O relatório do mês corrente carrega ao abrir; depois o usuário muda o período e clica em "Atualizar".
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function baixar() {
    try {
      const blob = await getBlob(`/relatorio-consumo-creditos/csv?${consulta(empresaFiltro ? { tenant_id: empresaFiltro } : {})}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `consumo-de-creditos-${inicio}-a-${fim}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível baixar a planilha."));
    }
  }

  const empresas = (dados?.empresas ?? []).filter((e) => !empresaFiltro || e.tenant_id === empresaFiltro);
  const aquisicoes = (dados?.aquisicoes ?? []).filter((a) => !empresaFiltro || a.tenant_id === empresaFiltro);

  return (
    <div className="p-5.5">
      <h1 className="mb-1 text-[18px] font-bold">Consumo de créditos</h1>
      <p className="mb-3 max-w-3xl text-[12px] text-muted">
        Créditos de IA e de enriquecimento são carteiras separadas. Aqui você vê o consumo por empresa e por usuário, a franquia e os limites do perfil contratado, o que
        foi consumido além da franquia e os créditos adicionais adquiridos.
      </p>

      <Card className="mb-3">
        <div className="flex flex-wrap items-end gap-2">
          <Input label="De" type="date" value={inicio} onChange={(ev) => setInicio(ev.target.value)} />
          <Input label="Até" type="date" value={fim} onChange={(ev) => setFim(ev.target.value)} />
          {(dados?.empresas.length ?? 0) > 1 && (
            <div>
              <label className="mb-1 block text-[10px] tracking-wide text-muted uppercase" htmlFor="rel-empresa">
                Empresa
              </label>
              <Select id="rel-empresa" value={empresaFiltro} onChange={(ev) => setEmpresaFiltro(ev.target.value)}>
                <option value="">Todas</option>
                {dados?.empresas.map((e) => (
                  <option key={e.tenant_id} value={e.tenant_id}>
                    {e.empresa}
                  </option>
                ))}
              </Select>
            </div>
          )}
          <Button size="sm" disabled={carregando} onClick={carregar}>
            {carregando ? "Gerando..." : "Atualizar"}
          </Button>
          <Button size="sm" variant="ghost" disabled={!dados} onClick={baixar}>
            Baixar planilha (CSV)
          </Button>
        </div>
        {erro && <p className="mt-2 text-[12px] text-red">{erro}</p>}
      </Card>

      {dados && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-5">
            <KpiCard label="IA consumida" value={num(dados.totais.ia.consumo_total)} sub={`${num(dados.totais.ia.consumo_adicional)} além da franquia`} />
            <KpiCard
              label="Decisores consumidos"
              value={num(dados.totais.contatos.consumo_total)}
              sub={`${num(dados.totais.contatos.consumo_adicional)} além da franquia`}
              colorClassName="text-violet"
            />
            <KpiCard label="Empresas" value={dados.totais.empresas} colorClassName="text-green" />
            <KpiCard label="Créditos adquiridos" value={num(dados.totais.aquisicoes.creditos)} sub={`${dados.totais.aquisicoes.quantidade} compra(s)`} colorClassName="text-amber" />
            <KpiCard label="Valor das aquisições" value={reais(dados.totais.aquisicoes.valor_brl)} colorClassName="text-amber" />
          </div>

          <Card className="mb-3">
            <SectionLabel>Por empresa</SectionLabel>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-border text-left text-[10px] tracking-wide text-muted uppercase">
                    <th className="p-1.5">Empresa / perfil</th>
                    <th className="p-1.5 text-right">IA franquia</th>
                    <th className="p-1.5 text-right">IA consumo</th>
                    <th className="p-1.5 text-right">IA adicional</th>
                    <th className="p-1.5">IA uso</th>
                    <th className="p-1.5 text-right">Decisores franquia</th>
                    <th className="p-1.5 text-right">Máx./pesquisa</th>
                    <th className="p-1.5 text-right">Decisores consumo</th>
                    <th className="p-1.5 text-right">Decisores adicional</th>
                    <th className="p-1.5">Decisores uso</th>
                  </tr>
                </thead>
                <tbody>
                  {empresas.map((e) => (
                    <Fragment key={e.tenant_id}>
                      <tr className="cursor-pointer border-b border-border hover:bg-surf2" onClick={() => setAberta(aberta === e.tenant_id ? null : e.tenant_id)}>
                        <td className="p-1.5">
                          <span className="mr-1 text-muted">{aberta === e.tenant_id ? "▾" : "▸"}</span>
                          <span className="font-semibold">{e.empresa}</span>
                          <span className="ml-2 text-muted">{e.plano ?? "sem plano"}</span>
                        </td>
                        <td className="p-1.5 text-right">{num(e.ia.franquia_mensal)}</td>
                        <td className="p-1.5 text-right">{num(e.ia.consumo_total)}</td>
                        <td className="p-1.5 text-right">{num(e.ia.consumo_adicional.total + e.ia.consumo_excedente.creditos)}</td>
                        <td className="p-1.5">
                          <Uso valor={e.ia.uso_da_franquia_percentual} />
                        </td>
                        <td className="p-1.5 text-right">{e.contatos.franquia_mensal ?? "—"}</td>
                        <td className="p-1.5 text-right">{e.contatos.limite_por_pesquisa ?? "—"}</td>
                        <td className="p-1.5 text-right">{num(e.contatos.consumo_total)}</td>
                        <td className="p-1.5 text-right">{num(e.contatos.consumo_adicional.total)}</td>
                        <td className="p-1.5">
                          <Uso valor={e.contatos.uso_da_franquia_percentual} />
                        </td>
                      </tr>
                      {aberta === e.tenant_id && (
                        <tr className="border-b border-border bg-surf2/50">
                          <td colSpan={10} className="p-3">
                            <Detalhe e={e} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                  {empresas.length === 0 && (
                    <tr>
                      <td colSpan={10} className="p-3 text-muted">
                        Nenhuma empresa no escopo.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-[11px] text-muted">Clique numa empresa para ver os usuários, os limites do perfil e o consumo adicional.</p>
          </Card>

          <Card className="mb-3">
            <SectionLabel>Aquisições de créditos adicionais</SectionLabel>
            {aquisicoes.length === 0 ? (
              <p className="text-[12px] text-muted">Nenhuma aquisição aprovada no período.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-[12px]">
                  <thead>
                    <tr className="border-b border-border text-left text-[10px] tracking-wide text-muted uppercase">
                      <th className="p-1.5">Data</th>
                      <th className="p-1.5">Empresa</th>
                      <th className="p-1.5">Produto</th>
                      <th className="p-1.5">Pacote</th>
                      <th className="p-1.5 text-right">Quantidade</th>
                      <th className="p-1.5 text-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aquisicoes.map((a, i) => (
                      <tr key={`${a.tenant_id}-${a.produto}-${a.data}-${i}`} className="border-b border-border">
                        <td className="p-1.5">{dia(a.data)}</td>
                        <td className="p-1.5">{a.empresa}</td>
                        <td className="p-1.5">
                          <Badge tone={a.produto === "IA" ? "cyan" : "violet"}>{a.produto}</Badge>
                        </td>
                        <td className="p-1.5">{a.pacote}</td>
                        <td className="p-1.5 text-right">{num(a.creditos)}</td>
                        <td className="p-1.5 text-right">{reais(a.valor_brl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-muted">
            {dados.notas.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Detalhe({ e }: { e: Empresa }) {
  const { ia, contatos } = e;
  return (
    <div className="grid grid-cols-1 gap-4 text-[12px] lg:grid-cols-2">
      <div>
        <p className="mb-1 font-semibold">Créditos de IA</p>
        <p className="mb-1 text-muted">
          Franquia contratada: {num(ia.franquia_mensal)} · da franquia: {num(ia.consumo_da_franquia)} · de pacotes comprados: {num(ia.consumo_adicional.pacotes_comprados)} · bônus/ajustes:{" "}
          {num(ia.consumo_adicional.bonus_e_ajustes)} · excedente pós-pago: {num(ia.consumo_excedente.creditos)} ({reais(ia.consumo_excedente.valor_brl)}) · expirado: {num(ia.expirado)} ·
          saldo: {num(ia.saldo_atual)}
        </p>
        <TabelaUsuarios
          linhas={ia.por_usuario.map((u) => ({ chave: String(u.usuario_id), nome: u.nome, papel: u.papel, creditos: u.creditos, extra: `${u.execucoes} execução(ões)` }))}
        />
      </div>
      <div>
        <p className="mb-1 font-semibold">Pesquisa de decisores</p>
        {contatos.sem_configuracao ? (
          <p className="mb-1 text-amber">Sem configuração de franquia neste perfil ({contatos.sem_configuracao.replaceAll("_", " ")}).</p>
        ) : (
          <p className="mb-1 text-muted">
            Franquia contratada: {contatos.franquia_mensal ?? "—"} · máx. por pesquisa: {contatos.limite_por_pesquisa ?? "—"} ({contatos.limite_por_pesquisa_origem}) · decisores por empresa:{" "}
            {contatos.decisores_por_empresa_max ?? "—"} · da franquia: {num(contatos.consumo_da_franquia)} · de pacotes comprados: {num(contatos.consumo_adicional.pacotes_comprados)} · outros:{" "}
            {num(contatos.consumo_adicional.outros)} · expirado: {num(contatos.expirado)} · saldo: {num(contatos.saldo_atual)}
          </p>
        )}
        <TabelaUsuarios
          linhas={contatos.por_usuario.map((u) => ({
            chave: String(u.usuario_id),
            nome: u.nome,
            papel: u.papel,
            creditos: u.creditos,
            extra: `${u.pesquisas} pesquisa(s) · ${u.empresas} empresa(s) · ${u.decisores} decisor(es)`,
          }))}
        />
      </div>
    </div>
  );
}

function TabelaUsuarios({ linhas }: { linhas: { chave: string; nome: string; papel: string | null; creditos: number; extra: string }[] }) {
  if (linhas.length === 0) return <p className="text-muted">Nenhum consumo por usuário no período.</p>;
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-border text-left text-[10px] tracking-wide text-muted uppercase">
          <th className="p-1">Usuário</th>
          <th className="p-1 text-right">Créditos</th>
          <th className="p-1">Detalhe</th>
        </tr>
      </thead>
      <tbody>
        {linhas.map((l) => (
          <tr key={l.chave} className="border-b border-border">
            <td className="p-1">
              {l.nome}
              {l.papel && <span className="ml-1 text-muted">({ROTULO_PAPEL[l.papel] ?? l.papel})</span>}
            </td>
            <td className="p-1 text-right font-semibold">{num(l.creditos)}</td>
            <td className="p-1 text-muted">{l.extra}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
