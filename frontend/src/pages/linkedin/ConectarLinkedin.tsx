import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, SectionLabel } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { SeletorArquivo } from "@/components/ui/SeletorArquivo";
import { api, mensagemErro } from "@/lib/api";

interface Status {
  total: number;
  atualizado_em: string | null;
}

interface Resultado {
  total_importado: number;
  lista_id: number | null;
  lista_nome: string | null;
  contas_criadas: number;
  contas_reaproveitadas: number;
  contatos_criados: number;
  contatos_atualizados: number;
  contatos_com_email: number;
  conexoes_sem_empresa: number;
  ia_disponivel: boolean;
  grupos_analisados: number;
  grupos_sem_analise: number;
  homonimos_mantidos_separados: number;
  variacoes_unificadas: { empresa: string; variacoes: string[] }[];
}

/** Conectar ao LinkedIn: o LinkedIn não permite que outro sistema entre na conta nem leia as conexões (login automático e raspagem causam banimento do perfil),
 * então a conexão é feita com o arquivo oficial de conexões que o próprio usuário baixa. Ao subir o arquivo, cada conexão vira contato, as empresas entram na
 * lista "Importação LinkedIn" sem duplicar e a IA confere os nomes parecidos. */
export function ConectarLinkedin() {
  const [status, setStatus] = useState<Status | null>(null);
  const [arquivo, setArquivo] = useState<{ nome: string; conteudo: string } | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api.get<Status>("/linkedin/conexoes/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  function selecionar(f: File) {
    const leitor = new FileReader();
    leitor.onload = () => setArquivo({ nome: f.name, conteudo: String(leitor.result ?? "") });
    leitor.readAsText(f);
  }

  async function importar() {
    if (!arquivo || importando) return;
    setImportando(true);
    setErro(null);
    setResultado(null);
    try {
      setResultado(await api.post<Resultado>("/linkedin/conexoes/importar", { conteudo_csv: arquivo.conteudo }));
      setArquivo(null);
      setStatus(await api.get<Status>("/linkedin/conexoes/status"));
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível importar as conexões."));
    } finally {
      setImportando(false);
    }
  }

  return (
    <div className="p-5.5">
      <h1 className="mb-1 text-[18px] font-bold">Conectar ao LinkedIn</h1>
      <p className="mb-3 max-w-3xl text-[12px] text-muted">
        Traga as suas conexões para o CRM. Cada conexão vira um contato (com cargo, e-mail quando houver e o link do perfil), e as empresas onde elas trabalham entram na
        lista <strong className="text-text">Importação LinkedIn</strong>, sem duplicar, para você prospectar.
      </p>

      <Card className="mb-3">
        <SectionLabel>Passo a passo</SectionLabel>
        <ol className="list-decimal space-y-1 pl-5 text-[12px]">
          <li>
            No LinkedIn, abra{" "}
            <a className="text-cyan underline" href="https://www.linkedin.com/mypreferences/d/download-my-data" target="_blank" rel="noreferrer">
              Configurações → Privacidade de dados → Obter uma cópia dos seus dados
            </a>
            , marque <strong>Conexões</strong> e peça o arquivo.
          </li>
          <li>Baixe o arquivo quando o LinkedIn avisar (costuma levar alguns minutos) e abra o ZIP: o que interessa é o <strong>Connections.csv</strong>.</li>
          <li>Envie o Connections.csv abaixo. Nada é enviado nem alterado na sua conta do LinkedIn.</li>
        </ol>
        <p className="mt-2 text-[11px] text-muted">
          Por que o arquivo? O LinkedIn não deixa sistemas externos acessar a conta nem listar conexões, e ferramentas que fazem isso por fora levam ao bloqueio do perfil.
          O arquivo oficial é a forma segura e permitida de trazer os seus contatos.
        </p>
      </Card>

      <Card className="mb-3">
        <SectionLabel>Importar conexões</SectionLabel>
        <p className="mb-2 text-[12px] text-muted">
          {status && status.total > 0
            ? `${status.total} conexões importadas${status.atualizado_em ? ` em ${new Date(status.atualizado_em).toLocaleString("pt-BR")}` : ""}. Importar de novo não duplica nada.`
            : "Nenhuma conexão importada ainda."}
        </p>
        <div className="flex flex-col gap-3 sm:max-w-md">
          <SeletorArquivo accept=".csv" onSelecionar={selecionar} />
          <Button type="button" disabled={!arquivo || importando} onClick={importar} className="w-full justify-center">
            {importando ? "Importando e conferindo as empresas..." : arquivo ? `Conectar e importar (${arquivo.nome})` : "Conectar e importar"}
          </Button>
        </div>
        {erro && <p className="mt-2 text-[12px] text-red">{erro}</p>}
      </Card>

      {resultado && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Contatos criados" value={resultado.contatos_criados} sub={`${resultado.contatos_atualizados} atualizados · ${resultado.contatos_com_email} com e-mail`} />
            <KpiCard label="Empresas novas" value={resultado.contas_criadas} colorClassName="text-violet" sub={`${resultado.contas_reaproveitadas} já existentes reaproveitadas`} />
            <KpiCard label="Conexões lidas" value={resultado.total_importado} colorClassName="text-green" sub={`${resultado.conexoes_sem_empresa} sem empresa informada`} />
            <KpiCard label="Nomes unificados pela IA" value={resultado.variacoes_unificadas.length} colorClassName="text-amber" sub={`${resultado.homonimos_mantidos_separados} grupo(s) mantidos separados`} />
          </div>

          <Card className="mb-3">
            <SectionLabel>O que foi feito</SectionLabel>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
              <Link className="text-cyan underline" to="/prospeccao">
                Abrir a lista “{resultado.lista_nome}” em Prospecção
              </Link>
              <span className="text-muted">·</span>
              <Link className="text-cyan underline" to="/leads/contatos">
                Ver os contatos
              </Link>
              <span className="text-muted">·</span>
              <Link className="text-cyan underline" to="/cadencias">
                Criar uma cadência para esta lista
              </Link>
            </div>
            {!resultado.ia_disponivel && (
              <p className="mb-2 rounded-md bg-surf2 p-2 text-[12px] text-amber">
                A IA não estava disponível para conferir {resultado.grupos_sem_analise} grupo(s) de empresas com nomes parecidos. Por segurança elas ficaram separadas; importe de novo
                mais tarde para tentar unificar.
              </p>
            )}
            {resultado.variacoes_unificadas.length > 0 && (
              <div className="mb-2">
                <p className="mb-1 font-semibold text-[12px]">Empresas unificadas pela IA (mesma empresa com nomes diferentes)</p>
                <ul className="space-y-0.5 text-[12px]">
                  {resultado.variacoes_unificadas.map((u) => (
                    <li key={u.empresa}>
                      <Badge tone="violet">{u.empresa}</Badge> <span className="text-muted">← {u.variacoes.join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-[11px] text-muted">
              Telefones: o arquivo do LinkedIn não traz telefone. Para buscá-los, abra a lista “Importação LinkedIn”, selecione as empresas e use “Pesquisar decisores” marcando
              <strong> Telefone</strong>. A busca respeita a franquia, o limite por pesquisa e os decisores por empresa do seu perfil contratado, e completa o contato quando o provedor
              devolve a mesma pessoa.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
