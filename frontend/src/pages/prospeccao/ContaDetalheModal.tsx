import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError, getBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface ContaCompleta {
  id: number;
  cnpj: string | null;
  nome: string;
  nome_fantasia: string | null;
  dominio: string | null;
  vendedor_usuario_id: number | null;
  porte: string | null;
  segmento: string | null;
  regiao: string | null;
  score_aderencia: number | null;
  status: string;
  motivo_descarte: string | null;
}

interface CampoEnriquecido {
  campo: string;
  valor: string;
  fonte: string;
  coletado_em: string;
}

interface Decisor {
  id: number;
  nome: string;
  cargo: string | null;
  canal_provavel: string | null;
  linkedin_url: string | null;
  email: string | null;
  telefone: string | null;
}

interface UsuarioResumo {
  id: number;
  nome: string;
}

interface ContaResumo {
  id: number;
  nome: string;
  nome_fantasia: string | null;
}

interface Props {
  contaId: number;
  onClose: () => void;
  onAtualizado: () => void;
}

export function ContaDetalheModal({ contaId, onClose, onAtualizado }: Props) {
  const { usuario } = useAuth();
  const isGestor = usuario?.papel === "admin" || usuario?.papel === "super_admin";
  const [conta, setConta] = useState<ContaCompleta | null>(null);
  const [campos, setCampos] = useState<CampoEnriquecido[]>([]);
  const [decisores, setDecisores] = useState<Decisor[]>([]);
  const [vendedores, setVendedores] = useState<UsuarioResumo[]>([]);
  const [todasAsContas, setTodasAsContas] = useState<ContaResumo[]>([]);
  const [mostrarDescarte, setMostrarDescarte] = useState(false);
  const [editandoConta, setEditandoConta] = useState(false);
  const [decisorEmEdicaoId, setDecisorEmEdicaoId] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState<string | null>(null);

  async function carregar() {
    try {
      const [contaResp, decisoresResp] = await Promise.all([
        api.get<ContaCompleta>(`/contas/${contaId}`),
        api.get<Decisor[]>(`/contas/${contaId}/decisores`),
      ]);
      setConta(contaResp);
      setDecisores(decisoresResp);
    } catch {
      setErro("Não foi possível carregar a conta.");
    }
  }

  useEffect(() => {
    carregar();
  }, [contaId]);

  useEffect(() => {
    api
      .get<ContaResumo[]>("/contas")
      .then(setTodasAsContas)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (isGestor) {
      api
        .get<UsuarioResumo[]>("/usuarios")
        .then(setVendedores)
        .catch(() => undefined);
    }
  }, [isGestor]);

  async function atribuirVendedor(vendedorUsuarioId: number | null) {
    await executar("atribuir-vendedor", async () => {
      await api.put(`/saude-contas/contas/${contaId}/vendedor`, { vendedor_usuario_id: vendedorUsuarioId });
      await carregar();
    });
  }

  async function executar(nomeAcao: string, acao: () => Promise<void>) {
    setErro(null);
    setCarregando(nomeAcao);
    try {
      await acao();
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
    } finally {
      setCarregando(null);
    }
  }

  async function priorizar() {
    await executar("priorizar", async () => {
      await api.post(`/contas/${contaId}/priorizar`);
      await carregar();
      onAtualizado();
    });
  }

  async function descartar(motivo: string) {
    await executar("descartar", async () => {
      await api.post(`/contas/${contaId}/descartar`, { motivo });
      setMostrarDescarte(false);
      await carregar();
      onAtualizado();
    });
  }

  async function salvarConta(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await executar("salvar-conta", async () => {
      await api.put(`/contas/${contaId}`, {
        nome: String(form.get("nome")),
        cnpj: String(form.get("cnpj") || "") || null,
        nome_fantasia: String(form.get("nome_fantasia") || "") || null,
        dominio: String(form.get("dominio") || "") || null,
        segmento: String(form.get("segmento") || "") || null,
        porte: String(form.get("porte") || "") || null,
        regiao: String(form.get("regiao") || "") || null,
      });
      setEditandoConta(false);
      await carregar();
      onAtualizado();
    });
  }

  async function salvarDecisor(decisorId: number, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const novaContaId = Number(form.get("conta_id"));
    await executar(`salvar-decisor-${decisorId}`, async () => {
      await api.put(`/contas/${contaId}/decisores/${decisorId}`, {
        nome: String(form.get("nome")),
        cargo: String(form.get("cargo") || "") || null,
        email: String(form.get("email") || "") || null,
        telefone: String(form.get("telefone") || "") || null,
        linkedin_url: String(form.get("linkedin_url") || "") || null,
        conta_id: novaContaId && novaContaId !== contaId ? novaContaId : null,
      });
      setDecisorEmEdicaoId(null);
      await carregar();
    });
  }

  async function enriquecerSite() {
    await executar("enriquecer-site", async () => {
      const resposta = await api.post<{ campos: CampoEnriquecido[] }>(`/contas/${contaId}/enriquecer`);
      setCampos(resposta.campos);
    });
  }

  async function enriquecerBrasilApi() {
    await executar("enriquecer-brasilapi", async () => {
      const resposta = await api.post<{ campos: CampoEnriquecido[] }>(`/contas/${contaId}/enriquecer-brasilapi`);
      setCampos(resposta.campos);
    });
  }

  async function mapearDecisores() {
    await executar("mapear-decisores", async () => {
      setDecisores(await api.post<Decisor[]>(`/contas/${contaId}/decisores/mapear`));
    });
  }

  async function exportarPdf() {
    await executar("exportar-pdf", async () => {
      const blob = await getBlob(`/contas/${contaId}/export/pdf`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `conta-${contaId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <Modal title={conta?.nome_fantasia || conta?.nome || "Conta"} open onClose={onClose}>
      {erro && <div className="mb-3 text-[12px] text-red">{erro}</div>}

      {conta && (
        <>
          {editandoConta ? (
            <form onSubmit={salvarConta} className="mb-4 flex flex-col gap-3">
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Razão social</div>
                <Input name="nome" required defaultValue={conta.nome} placeholder="Razão social" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Nome fantasia</div>
                <Input name="nome_fantasia" defaultValue={conta.nome_fantasia ?? ""} placeholder="Marca comercial, se diferente da razão social" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">CNPJ</div>
                <Input name="cnpj" defaultValue={conta.cnpj ?? ""} placeholder="00.000.000/0000-00" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Domínio (site)</div>
                <Input name="dominio" defaultValue={conta.dominio ?? ""} placeholder="empresa.com.br" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Segmento</div>
                <Input name="segmento" defaultValue={conta.segmento ?? ""} placeholder="Ex.: Tecnologia" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Porte</div>
                <Input name="porte" defaultValue={conta.porte ?? ""} placeholder="Ex.: PEQUENO" />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Região</div>
                <Input name="regiao" defaultValue={conta.regiao ?? ""} placeholder="Ex.: SP" />
              </div>
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={carregando !== null}>
                  {carregando === "salvar-conta" ? "Salvando..." : "Salvar"}
                </Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => setEditandoConta(false)}>
                  Cancelar
                </Button>
              </div>
            </form>
          ) : (
            <div className="mb-4">
              <div className="mb-2 grid grid-cols-2 gap-2 text-[11px] text-muted">
                <div>Razão social: {conta.nome}</div>
                <div>Nome fantasia: {conta.nome_fantasia ?? "—"}</div>
                <div>CNPJ: {conta.cnpj ?? "—"}</div>
                <div>Domínio: {conta.dominio ?? "—"}</div>
                <div>Porte: {conta.porte ?? "—"}</div>
                <div>Segmento: {conta.segmento ?? "—"}</div>
                <div>
                  Status: <Badge tone={conta.status === "priorizada" ? "green" : "cyan"}>{conta.status}</Badge>
                </div>
                <div>Score: {conta.score_aderencia ?? "—"}</div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setEditandoConta(true)}>
                Editar dados da conta
              </Button>
            </div>
          )}

          <div className="mb-4">
            <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">
              Vendedor responsável (MAP)
            </div>
            {isGestor ? (
              <Select
                value={conta.vendedor_usuario_id ?? ""}
                onChange={(event) =>
                  atribuirVendedor(event.target.value ? Number(event.target.value) : null)
                }
                disabled={carregando !== null}
              >
                <option value="">Sem vendedor atribuído</option>
                {vendedores.map((vendedor) => (
                  <option key={vendedor.id} value={vendedor.id}>
                    {vendedor.nome}
                  </option>
                ))}
              </Select>
            ) : (
              <div className="text-[11px] text-muted">
                {conta.vendedor_usuario_id === null
                  ? "Sem vendedor atribuído"
                  : conta.vendedor_usuario_id === usuario?.id
                    ? "Atribuído a você"
                    : "Atribuído a outro vendedor"}
              </div>
            )}
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <Button size="sm" variant="green" disabled={carregando !== null} onClick={priorizar}>
              Priorizar
            </Button>
            <Button size="sm" variant="danger" disabled={carregando !== null} onClick={() => setMostrarDescarte(true)}>
              Descartar
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={enriquecerSite}>
              Pesquisar empresa (site)
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={enriquecerBrasilApi}>
              Enriquecer (BrasilAPI)
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={mapearDecisores}>
              Mapear decisores
            </Button>
            <Button size="sm" variant="ghost" disabled={carregando !== null} onClick={exportarPdf}>
              Exportar PDF
            </Button>
          </div>
          <div className="mb-4 text-[11px] text-muted">
            "Pesquisar empresa (site)" varre a home e páginas internas (sobre,
            investidores, notícias, privacidade) do domínio cadastrado e pede à
            IA um resumo de porte, crescimento, marcos, novos projetos e se há
            política de privacidade/LGPD publicada — serve de insumo para
            qualquer oferta, não só para prospecção de LGPD.
          </div>

          {mostrarDescarte && (
            <form
              className="mb-4 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const motivo = new FormData(event.currentTarget).get("motivo");
                descartar(String(motivo ?? ""));
              }}
            >
              <Input name="motivo" required placeholder="Motivo do descarte" className="flex-1" />
              <Button size="sm" variant="danger" type="submit">
                Confirmar
              </Button>
            </form>
          )}

          {campos.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Campos enriquecidos</div>
              <div className="flex flex-col gap-1 text-[11px]">
                {campos.map((campo, indice) => (
                  <div key={indice} className="flex justify-between border-b border-border py-1">
                    <span className="text-text">{campo.campo}</span>
                    <span className="text-muted">{campo.valor}</span>
                    <Badge tone="muted">{campo.fonte}</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          {decisores.length > 0 && (
            <div>
              <div className="mb-1.5 text-[10px] tracking-wide text-muted uppercase">Decisores</div>
              <div className="flex flex-col gap-2 text-[11px]">
                {decisores.map((decisor) =>
                  decisorEmEdicaoId === decisor.id ? (
                    <form
                      key={decisor.id}
                      onSubmit={(event) => salvarDecisor(decisor.id, event)}
                      className="flex flex-col gap-2 rounded-lg border border-border p-2.5"
                    >
                      <Input name="nome" required defaultValue={decisor.nome} placeholder="Nome" />
                      <Input name="cargo" defaultValue={decisor.cargo ?? ""} placeholder="Cargo" />
                      <Input name="email" type="email" defaultValue={decisor.email ?? ""} placeholder="E-mail" />
                      <Input name="telefone" defaultValue={decisor.telefone ?? ""} placeholder="Telefone" />
                      <Input name="linkedin_url" defaultValue={decisor.linkedin_url ?? ""} placeholder="LinkedIn (URL)" />
                      <div>
                        <div className="mb-1 text-[10px] tracking-wide text-muted uppercase">Empresa vinculada</div>
                        <Select name="conta_id" defaultValue={contaId}>
                          {todasAsContas.map((opcao) => (
                            <option key={opcao.id} value={opcao.id}>
                              {opcao.nome_fantasia || opcao.nome}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" type="submit" disabled={carregando !== null}>
                          {carregando === `salvar-decisor-${decisor.id}` ? "Salvando..." : "Salvar"}
                        </Button>
                        <Button size="sm" variant="ghost" type="button" onClick={() => setDecisorEmEdicaoId(null)}>
                          Cancelar
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div key={decisor.id} className="flex items-center justify-between border-b border-border py-1">
                      <div>
                        <span className="font-semibold text-text">{decisor.nome}</span>
                        {decisor.cargo && <span className="text-muted"> · {decisor.cargo}</span>}
                        {decisor.email && <span className="text-muted"> · {decisor.email}</span>}
                        {decisor.telefone && <span className="text-muted"> · {decisor.telefone}</span>}
                        {decisor.canal_provavel && <span className="text-muted"> · canal: {decisor.canal_provavel}</span>}
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => setDecisorEmEdicaoId(decisor.id)}>
                        Editar
                      </Button>
                    </div>
                  ),
                )}
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
