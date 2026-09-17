import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { PerfilEmpresa } from "@/pages/rede-social/RedeSocial";

const ROTULOS_VERIFICACAO: Record<string, { texto: string; tone: "green" | "amber" | "muted" | "red" }> = {
  verificada: { texto: "Verificada", tone: "green" },
  pendente: { texto: "Verificação em análise", tone: "amber" },
  rejeitada: { texto: "Verificação recusada", tone: "red" },
  nao_verificada: { texto: "Não verificada", tone: "muted" },
};

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
  if (perfil === null) return null;
  const verificacao = ROTULOS_VERIFICACAO[perfil.status_verificacao] ?? ROTULOS_VERIFICACAO.nao_verificada;

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
      </div>
    </Modal>
  );
}
