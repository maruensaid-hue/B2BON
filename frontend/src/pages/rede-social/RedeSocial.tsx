import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConversaModal } from "@/pages/rede-social/ConversaModal";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface PerfilEmpresa {
  tenant_id: string;
  nome_exibicao: string;
  descricao: string | null;
  setor: string | null;
  site: string | null;
}

interface OfertaResumo {
  nome: string;
  descricao: string;
}

interface EmpresaDiretorio {
  perfil: PerfilEmpresa;
  status_conexao: "nenhuma" | "pendente_enviada" | "pendente_recebida" | "aceita";
  oferta_principal: OfertaResumo | null;
}

interface Conexao {
  id: number;
  tenant_id_origem: string;
  tenant_id_destino: string;
  status: string;
}

export function RedeSocial() {
  const { usuario } = useAuth();
  const [perfil, setPerfil] = useState<PerfilEmpresa | null>(null);
  const [empresas, setEmpresas] = useState<EmpresaDiretorio[]>([]);
  const [conexoesPendentes, setConexoesPendentes] = useState<Conexao[]>([]);
  const [modalPerfilAberto, setModalPerfilAberto] = useState(false);
  const [conversaTenantId, setConversaTenantId] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function carregarTudo() {
    try {
      const [perfilResp, empresasResp, conexoesResp] = await Promise.all([
        api.get<PerfilEmpresa>("/rede-social/perfil"),
        api.get<EmpresaDiretorio[]>("/rede-social/empresas"),
        api.get<Conexao[]>("/rede-social/conexoes?status=pendente"),
      ]);
      setPerfil(perfilResp);
      setEmpresas(empresasResp);
      setConexoesPendentes(conexoesResp);
    } catch {
      setErro("Não foi possível carregar a Rede Social.");
    }
  }

  useEffect(() => {
    carregarTudo();
  }, []);

  function conexaoRecebidaDe(tenantId: string): Conexao | undefined {
    return conexoesPendentes.find(
      (conexao) => conexao.tenant_id_origem === tenantId && conexao.tenant_id_destino === usuario?.tenant_id,
    );
  }

  async function salvarPerfil(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api.put("/rede-social/perfil", {
        nome_exibicao: String(form.get("nome_exibicao")),
        descricao: String(form.get("descricao") || "") || null,
        setor: String(form.get("setor") || "") || null,
        site: String(form.get("site") || "") || null,
      });
      setModalPerfilAberto(false);
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar o perfil.");
    }
  }

  async function conectar(tenantId: string) {
    try {
      await api.post("/rede-social/conexoes", { tenant_id_destino: tenantId });
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível solicitar a conexão.");
    }
  }

  async function responder(conexaoId: number, aceitar: boolean) {
    try {
      await api.put(`/rede-social/conexoes/${conexaoId}`, { aceitar });
      await carregarTudo();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível responder à conexão.");
    }
  }

  return (
    <div className="p-5.5">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <div className="font-head text-xl font-bold">Rede Social</div>
          <div className="mt-0.5 text-[11px] text-muted">Perfil, diretório e mensageria B2B ON</div>
        </div>
      </div>

      {erro && <div className="mb-4 text-[12px] text-red">{erro}</div>}

      <Card className="mb-4">
        <div className="flex items-start justify-between">
          <div>
            <SectionLabel>Meu perfil</SectionLabel>
            <div className="text-[14px] font-bold">{perfil?.nome_exibicao}</div>
            <div className="mt-1 text-[11px] text-muted">
              {perfil?.setor ?? "Sem setor"} {perfil?.site ? `· ${perfil.site}` : ""}
            </div>
            {perfil?.descricao && <div className="mt-1 text-[11px] text-muted">{perfil.descricao}</div>}
          </div>
          <Button size="sm" variant="ghost" onClick={() => setModalPerfilAberto(true)}>
            Editar
          </Button>
        </div>
      </Card>

      {conexoesPendentes.filter((conexao) => conexao.tenant_id_destino === usuario?.tenant_id).length > 0 && (
        <Card className="mb-4">
          <SectionLabel>Conexões pendentes</SectionLabel>
          <div className="flex flex-col gap-2">
            {conexoesPendentes
              .filter((conexao) => conexao.tenant_id_destino === usuario?.tenant_id)
              .map((conexao) => {
              const outroTenant =
                empresas.find((empresa) => empresa.perfil.tenant_id === conexao.tenant_id_origem)?.perfil
                  .nome_exibicao ?? conexao.tenant_id_origem;
              return (
                <div key={conexao.id} className="flex items-center justify-between text-[12px]">
                  <span>{outroTenant}</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="green" onClick={() => responder(conexao.id, true)}>
                      Aceitar
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => responder(conexao.id, false)}>
                      Recusar
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card>
        <SectionLabel>Diretório de empresas</SectionLabel>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {empresas.map((empresa) => (
            <div key={empresa.perfil.tenant_id} className="rounded-xl border border-border bg-surf2 p-3.5">
              <div className="mb-1 flex items-center justify-between">
                <div className="text-[13px] font-bold">{empresa.perfil.nome_exibicao}</div>
                <Badge tone={empresa.status_conexao === "aceita" ? "green" : "muted"}>
                  {empresa.status_conexao}
                </Badge>
              </div>
              <div className="mb-2 text-[11px] text-muted">{empresa.perfil.setor ?? "—"}</div>
              {empresa.oferta_principal && (
                <div className="mb-2 text-[11px] text-muted">
                  <span className="font-semibold text-text">{empresa.oferta_principal.nome}</span> —{" "}
                  {empresa.oferta_principal.descricao}
                </div>
              )}

              {empresa.status_conexao === "nenhuma" && (
                <Button size="sm" onClick={() => conectar(empresa.perfil.tenant_id)}>
                  Conectar
                </Button>
              )}
              {empresa.status_conexao === "pendente_enviada" && (
                <Badge tone="amber">Pendente (enviada)</Badge>
              )}
              {empresa.status_conexao === "pendente_recebida" && (
                <div className="flex gap-2">
                  {(() => {
                    const conexao = conexaoRecebidaDe(empresa.perfil.tenant_id);
                    if (!conexao) return null;
                    return (
                      <>
                        <Button size="sm" variant="green" onClick={() => responder(conexao.id, true)}>
                          Aceitar
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => responder(conexao.id, false)}>
                          Recusar
                        </Button>
                      </>
                    );
                  })()}
                </div>
              )}
              {empresa.status_conexao === "aceita" && (
                <Button size="sm" variant="ghost" onClick={() => setConversaTenantId(empresa.perfil.tenant_id)}>
                  Mensagens
                </Button>
              )}
            </div>
          ))}
          {empresas.length === 0 && (
            <div className="text-[12px] text-muted">Nenhuma outra empresa cadastrada na rede ainda.</div>
          )}
        </div>
      </Card>

      <Modal title="Editar perfil" open={modalPerfilAberto} onClose={() => setModalPerfilAberto(false)}>
        <form onSubmit={salvarPerfil} className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome de exibição</div>
            <Input name="nome_exibicao" required defaultValue={perfil?.nome_exibicao} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Setor</div>
            <Input name="setor" defaultValue={perfil?.setor ?? ""} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Site</div>
            <Input name="site" defaultValue={perfil?.site ?? ""} />
          </div>
          <div>
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Descrição</div>
            <Input name="descricao" defaultValue={perfil?.descricao ?? ""} />
          </div>
          <Button type="submit" className="w-full justify-center">
            Salvar
          </Button>
        </form>
      </Modal>

      {conversaTenantId !== null && (
        <ConversaModal
          tenantId={conversaTenantId}
          nomeExibicao={
            empresas.find((empresa) => empresa.perfil.tenant_id === conversaTenantId)?.perfil.nome_exibicao ??
            conversaTenantId
          }
          onClose={() => setConversaTenantId(null)}
        />
      )}
    </div>
  );
}
