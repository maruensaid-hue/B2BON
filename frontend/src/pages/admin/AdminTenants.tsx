import { useEffect, useState, type FormEvent, type ReactElement } from "react";

import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { AcessoRestrito } from "@/pages/admin/AcessoRestrito";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Tenant {
  id: string;
  razao_social: string;
  cnpj: string | null;
  criado_em: string;
  tipo: string;
  tenant_pai_id: string | null;
  modo_cobranca: string;
}

interface Plano {
  id: number;
  nome: string;
  franquia_contas_mes: number;
  max_usuarios: number;
  preco_mensal: number;
}

interface NoArvore {
  tenant: Tenant;
  filhos: NoArvore[];
}

const COR_TIPO: Record<string, string> = {
  distribuidor: "text-violet",
  revendedor: "text-cyan",
  cliente: "text-muted",
};

/** Monta a árvore a partir da lista plana que a API devolve — a "raiz" de
 * cada visão é o próprio tenant logado (um Revendedor não enxerga o
 * Distribuidor acima dele, só a própria subárvore, então o pai dele fica
 * fora do conjunto e ele vira raiz aqui). */
function construirArvore(tenants: Tenant[]): NoArvore[] {
  const idsVisiveis = new Set(tenants.map((t) => t.id));
  const filhosPorPai = new Map<string, Tenant[]>();
  const raizes: Tenant[] = [];

  for (const tenant of tenants) {
    if (tenant.tenant_pai_id && idsVisiveis.has(tenant.tenant_pai_id)) {
      const lista = filhosPorPai.get(tenant.tenant_pai_id) ?? [];
      lista.push(tenant);
      filhosPorPai.set(tenant.tenant_pai_id, lista);
    } else {
      raizes.push(tenant);
    }
  }

  const montarNo = (tenant: Tenant): NoArvore => ({
    tenant,
    filhos: (filhosPorPai.get(tenant.id) ?? []).map(montarNo),
  });

  return raizes.map(montarNo);
}

export function AdminTenants() {
  const { usuario } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Recolhido é a exceção (guardamos só quem foi fechado) — assim um
  // tenant novo criado depois já aparece expandido por padrão, sem
  // precisar re-sincronizar esse estado com a lista toda vez que recarrega.
  const [recolhidos, setRecolhidos] = useState<Set<string>>(new Set());

  function alternarExpandido(tenantId: string) {
    setRecolhidos((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(tenantId)) proximo.delete(tenantId);
      else proximo.add(tenantId);
      return proximo;
    });
  }

  const isSuperAdmin = usuario?.papel === "super_admin";
  // Distribuidor/revendedor logados gerenciam a própria subárvore, igual a
  // um super_admin só que escopado — o backend (listar_tenants_visiveis)
  // já filtra o que essa mesma tela recebe (raio-X: hierarquia).
  const ehGestorHierarquico = usuario?.papel === "admin" && ["distribuidor", "revendedor"].includes(usuario.tenant_tipo);
  const podeGerenciar = isSuperAdmin || ehGestorHierarquico;
  // Tipo do tenant que este gestor tem permissão de criar diretamente sob
  // si mesmo (distribuidor cria revendedor, revendedor cria cliente) — só
  // super_admin escolhe o tipo livremente.
  const tipoFilho = usuario?.tenant_tipo === "distribuidor" ? "revendedor" : "cliente";

  function renderNos(nos: NoArvore[], profundidade: number): ReactElement[] {
    return nos.flatMap(({ tenant, filhos }) => {
      const temFilhos = filhos.length > 0;
      const recolhido = recolhidos.has(tenant.id);
      const linha = (
        <tr key={tenant.id} className="border-b border-border">
          <td className="p-2 font-semibold">
            <span style={{ paddingLeft: profundidade * 18 }} className="inline-flex items-center gap-1.5">
              {temFilhos ? (
                <button
                  type="button"
                  onClick={() => alternarExpandido(tenant.id)}
                  className="w-3.5 text-muted hover:text-text"
                  aria-label={recolhido ? "Expandir" : "Recolher"}
                >
                  {recolhido ? "▸" : "▾"}
                </button>
              ) : (
                <span className="w-3.5" />
              )}
              {tenant.id}
            </span>
          </td>
          <td className="p-2">{tenant.razao_social}</td>
          <td className={`p-2 capitalize ${COR_TIPO[tenant.tipo] ?? "text-muted"}`}>{tenant.tipo}</td>
          <td className="p-2 text-muted">{tenant.cnpj ?? "—"}</td>
          <td className="p-2 text-muted">{new Date(tenant.criado_em).toLocaleDateString("pt-BR")}</td>
        </tr>
      );
      return recolhido ? [linha] : [linha, ...renderNos(filhos, profundidade + 1)];
    });
  }

  async function carregar() {
    try {
      const [tenantsResp, planosResp] = await Promise.all([
        api.get<Tenant[]>("/admin/tenants"),
        api.get<Plano[]>("/planos"),
      ]);
      setTenants(tenantsResp);
      setPlanos(planosResp);
    } catch {
      setErro("Não foi possível carregar os tenants.");
    }
  }

  useEffect(() => {
    if (podeGerenciar) carregar();
  }, [podeGerenciar]);

  async function criarTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.post("/admin/tenants", {
        tenant_id: String(form.get("tenant_id")),
        razao_social: String(form.get("razao_social")),
        cnpj: String(form.get("cnpj") || "") || null,
        plano_id: Number(form.get("plano_id")),
        nome_admin: String(form.get("nome_admin")),
        email_admin: String(form.get("email_admin")),
        senha_admin: String(form.get("senha_admin")),
        tenant_pai_id: isSuperAdmin ? String(form.get("tenant_pai_id") || "") || null : usuario!.tenant_id,
        tipo: isSuperAdmin ? String(form.get("tipo") || "cliente") : tipoFilho,
      });
      setModalAberto(false);
      await carregar();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o tenant.");
    }
  }

  if (!podeGerenciar) return <AcessoRestrito />;

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Admin — Tenants</div>
          <div className="mt-0.5 text-[11px] text-muted">Assinantes da B2B ON</div>
        </div>
        <Button size="sm" variant="violet" onClick={() => setModalAberto(true)}>
          + Criar tenant
        </Button>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card>
        <SectionLabel>Tenants</SectionLabel>
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-[9.5px] tracking-wide text-muted uppercase">
              <th className="p-2 text-left">ID</th>
              <th className="p-2 text-left">Razão social</th>
              <th className="p-2 text-left">Tipo</th>
              <th className="p-2 text-left">CNPJ</th>
              <th className="p-2 text-left">Criado em</th>
            </tr>
          </thead>
          <tbody>
            {renderNos(construirArvore(tenants), 0)}
            {tenants.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-muted">
                  Nenhum tenant cadastrado ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Modal title="Criar tenant" open={modalAberto} onClose={() => setModalAberto(false)}>
        <form onSubmit={criarTenant} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Identificador (slug)</div>
            <Input name="tenant_id" required placeholder="ex: empresa-x" />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Razão social</div>
            <Input name="razao_social" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ (opcional)</div>
            <Input name="cnpj" />
          </div>
          {isSuperAdmin ? (
            <>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Tipo</div>
                <Select name="tipo" defaultValue="cliente">
                  <option value="distribuidor">Distribuidor</option>
                  <option value="cliente">Cliente (direto, sem revenda)</option>
                </Select>
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
                  Tenant pai (opcional — id do distribuidor/revendedor)
                </div>
                <Input name="tenant_pai_id" placeholder="deixe em branco pra tenant top-level" />
              </div>
            </>
          ) : (
            <div className="text-[11px] text-muted">
              Criado como <span className="capitalize">{tipoFilho}</span> sob o seu tenant ({usuario!.tenant_id}).
            </div>
          )}
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Plano</div>
            <Select name="plano_id" required defaultValue="">
              <option value="" disabled>
                Selecione...
              </option>
              {planos.map((plano) => (
                <option key={plano.id} value={plano.id}>
                  {plano.nome} — R${plano.preco_mensal}/mês
                </option>
              ))}
            </Select>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome do admin</div>
            <Input name="nome_admin" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">E-mail do admin</div>
            <Input name="email_admin" type="email" required />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Senha do admin</div>
            <Input name="senha_admin" type="password" required minLength={8} />
          </div>
          <Button type="submit" className="mt-1 w-full justify-center">
            Criar
          </Button>
        </form>
      </Modal>
    </div>
  );
}
