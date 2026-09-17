import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { PerfilEmpresa } from "@/pages/rede-social/RedeSocial";
import { api, ApiError } from "@/lib/api";

const ROTULOS_VERIFICACAO: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  verificada: { texto: "Verificada", tone: "green" },
  pendente: { texto: "Verificação em análise", tone: "amber" },
  rejeitada: { texto: "Verificação recusada", tone: "red" },
  nao_verificada: { texto: "Não verificada", tone: "muted" },
};

const ROTULOS_RELACIONAMENTO: Record<string, string> = {
  SUPPLIER_OF: "Somos fornecedores desta empresa",
  CUSTOMER_OF: "Somos clientes desta empresa",
  PARTNER_OF: "Somos parceiros desta empresa",
  RESELLER_OF: "Somos revendedores desta empresa",
  DISTRIBUTOR_OF: "Somos distribuidores desta empresa",
  INTEGRATES_WITH: "Integramos com esta empresa",
  USES_TECHNOLOGY: "Usamos tecnologia desta empresa",
  PROVIDES_SERVICE: "Prestamos serviço para esta empresa",
  PROVIDES_PRODUCT: "Fornecemos produto para esta empresa",
  INVESTS_IN: "Investimos nesta empresa",
  INTERESTED_IN: "Temos interesse nesta empresa",
  LOOKING_FOR: "Estamos buscando algo desta empresa",
};

interface RelacionamentoEmpresarial {
  id: number;
  tenant_id_origem: string;
  tenant_id_destino: string;
  outro_tenant_nome: string;
  tipo: string;
  visibilidade: string;
  confianca: "autodeclarada" | "confirmada_pela_contraparte";
  pode_confirmar: boolean;
  criado_em: string;
}

function ListaChips({ titulo, itens }: { titulo: string; itens: string[] }) {
  if (itens.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">{titulo}</div>
      <div className="flex flex-wrap gap-1.5">
        {itens.map((item) => (
          <Badge key={item} tone="violet">
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export function PerfilEmpresaDetalheModal({
  perfil,
  onClose,
}: {
  perfil: PerfilEmpresa | null;
  onClose: () => void;
}) {
  const [relacionamentos, setRelacionamentos] = useState<RelacionamentoEmpresarial[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [declarando, setDeclarando] = useState(false);
  const [confirmandoId, setConfirmandoId] = useState<number | null>(null);

  async function carregarRelacionamentos(tenantId: string) {
    try {
      setRelacionamentos(await api.get<RelacionamentoEmpresarial[]>(`/rede-social/relacionamentos/${tenantId}`));
    } catch {
      setErro("Não foi possível carregar os relacionamentos comerciais.");
    }
  }

  useEffect(() => {
    if (perfil) carregarRelacionamentos(perfil.tenant_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perfil?.tenant_id]);

  if (perfil === null) return null;
  const verificacao = ROTULOS_VERIFICACAO[perfil.status_verificacao] ?? ROTULOS_VERIFICACAO.nao_verificada;

  async function declarar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (declarando) return;
    const form = new FormData(event.currentTarget);
    setDeclarando(true);
    setErro(null);
    try {
      await api.post("/rede-social/relacionamentos", {
        tenant_id_destino: perfil!.tenant_id,
        tipo: String(form.get("tipo")),
      });
      await carregarRelacionamentos(perfil!.tenant_id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível declarar o relacionamento.");
    } finally {
      setDeclarando(false);
    }
  }

  async function confirmar(relacionamentoId: number) {
    setConfirmandoId(relacionamentoId);
    setErro(null);
    try {
      await api.post(`/rede-social/relacionamentos/${relacionamentoId}/confirmar`);
      await carregarRelacionamentos(perfil!.tenant_id);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível confirmar o relacionamento.");
    } finally {
      setConfirmandoId(null);
    }
  }

  return (
    <Modal title={perfil.nome_exibicao} open onClose={onClose}>
      <div className="flex flex-col gap-4">
        {perfil.capa_url && (
          <img src={perfil.capa_url} alt="" className="h-24 w-full rounded-lg object-cover" />
        )}
        <div className="flex items-center gap-3">
          {perfil.logo_url && (
            <img src={perfil.logo_url} alt="" className="h-12 w-12 rounded-lg border border-border object-cover" />
          )}
          <div>
            <Badge tone={verificacao.tone}>{verificacao.texto}</Badge>
          </div>
        </div>

        {erro && <div className="text-[12px] text-red">{erro}</div>}

        {perfil.descricao && <div className="text-[12px] text-text">{perfil.descricao}</div>}

        <div className="grid grid-cols-2 gap-3 text-[12px]">
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Setor</div>
            <div>{perfil.setor ?? "—"}</div>
          </div>
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Porte</div>
            <div>{perfil.porte ?? "—"}</div>
          </div>
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">CNAE principal</div>
            <div>{perfil.cnae_principal ?? "—"}</div>
          </div>
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Sede</div>
            <div>
              {perfil.sede_cidade || perfil.sede_uf
                ? `${perfil.sede_cidade ?? ""}${perfil.sede_cidade && perfil.sede_uf ? " · " : ""}${perfil.sede_uf ?? ""}`
                : "—"}
            </div>
          </div>
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Site</div>
            <div>{perfil.site ?? "—"}</div>
          </div>
          <div>
            <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">LinkedIn</div>
            <div>{perfil.redes_sociais?.linkedin ?? "—"}</div>
          </div>
        </div>

        <ListaChips titulo="Mercados atendidos" itens={perfil.mercados} />
        <ListaChips titulo="Produtos/serviços" itens={perfil.produtos_servicos} />
        <ListaChips titulo="Tecnologias" itens={perfil.tecnologias} />
        <ListaChips titulo="Certificações" itens={perfil.certificacoes} />

        <div>
          <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Relacionamentos comerciais</div>
          <div className="flex flex-col gap-1.5">
            {relacionamentos.map((relacionamento) => (
              <div key={relacionamento.id} className="flex items-center justify-between gap-2 rounded-lg border border-border p-2 text-[11px]">
                <span>{ROTULOS_RELACIONAMENTO[relacionamento.tipo] ?? relacionamento.tipo}</span>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <Badge tone={relacionamento.confianca === "confirmada_pela_contraparte" ? "green" : "muted"}>
                    {relacionamento.confianca === "confirmada_pela_contraparte" ? "Confirmado" : "Autodeclarado"}
                  </Badge>
                  {relacionamento.pode_confirmar && (
                    <Button
                      size="sm"
                      variant="green"
                      disabled={confirmandoId === relacionamento.id}
                      onClick={() => confirmar(relacionamento.id)}
                    >
                      Confirmar
                    </Button>
                  )}
                </div>
              </div>
            ))}
            {relacionamentos.length === 0 && (
              <div className="text-[11px] text-muted">Nenhum relacionamento comercial declarado ainda.</div>
            )}
          </div>
          <form onSubmit={declarar} className="mt-2 flex gap-2">
            <Select name="tipo" className="flex-1">
              {Object.entries(ROTULOS_RELACIONAMENTO).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
            <Button type="submit" size="sm" disabled={declarando}>
              {declarando ? "Declarando..." : "Declarar"}
            </Button>
          </form>
        </div>
      </div>
    </Modal>
  );
}
