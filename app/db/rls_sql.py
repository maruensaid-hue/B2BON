"""SQL das políticas de RLS (D-110): funções auxiliares, políticas por tipo de tabela e a remoção (reversão). Só devolve texto; quem executa é a migração (`op.execute`) ou os testes.

Convenções
- Toda política se chama `rls_<tipo>[_<nome>]`; a reversão remove qualquer política `rls\\_%` da tabela, então não depende de saber o que foi criado.
- As funções leem as variáveis de sessão gravadas por `app/db/rls.py` (`app.tenant_id`, `app.escopo`, `app.visiveis`, `app.chave`). Variável ausente ou vazia vira `NULL`, e
  `NULL` nunca é igual a nada: sem contexto, as políticas negam.
- Funções `SECURITY DEFINER` (só as de escopo herdado e a da redefinição de senha) leem a tabela-pai sem passar pelo RLS dela, para evitar recursão entre políticas; cada uma
  devolve só um booleano e fixa o `search_path`.
"""

from __future__ import annotations

import re

FUNCOES_BASE = (
    "CREATE OR REPLACE FUNCTION b2bon_tenant() RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '') $$",
    "CREATE OR REPLACE FUNCTION b2bon_escopo() RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.escopo', true), '') $$",
    "CREATE OR REPLACE FUNCTION b2bon_chave() RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.chave', true), '') $$",
    """CREATE OR REPLACE FUNCTION b2bon_visivel(tenant text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN current_setting('app.visiveis', true) = '*' THEN b2bon_escopo() = 'tenant'
                ELSE b2bon_escopo() = 'tenant' AND tenant = ANY(string_to_array(NULLIF(current_setting('app.visiveis', true), ''), ',')) END $$""",
)

_DEFINER = "SECURITY DEFINER STABLE SET search_path = public, pg_temp"

# Funções que leem a tabela-pai sem o RLS dela. (nome, SQL do corpo; `$1` é o id do pai)
FUNCOES_DO_PAI = {
    "b2bon_conta_do_tenant": "SELECT EXISTS (SELECT 1 FROM conta WHERE id = $1 AND tenant_id = b2bon_tenant())",
    "b2bon_post_do_tenant": "SELECT EXISTS (SELECT 1 FROM post_rede_social WHERE id = $1 AND tenant_id = b2bon_tenant())",
    "b2bon_sala_do_tenant": "SELECT EXISTS (SELECT 1 FROM sala_corporativa WHERE id = $1 AND (tenant_id_a = b2bon_tenant() OR tenant_id_b = b2bon_tenant()))",
    "b2bon_usuario_do_tenant": "SELECT EXISTS (SELECT 1 FROM usuario WHERE id = $1 AND tenant_id = b2bon_tenant())",
    "b2bon_usuario_tem_redefinicao": "SELECT EXISTS (SELECT 1 FROM redefinicao_senha r WHERE r.usuario_id = $1 AND r.token = b2bon_chave())",
}


def sql_funcoes() -> list[str]:
    comandos = list(FUNCOES_BASE)
    for nome, corpo in FUNCOES_DO_PAI.items():
        comandos.append(f"CREATE OR REPLACE FUNCTION {nome}(integer) RETURNS boolean LANGUAGE sql {_DEFINER} AS $$ {corpo} $$")
    return comandos


def sql_remover_funcoes() -> list[str]:
    nomes = ["b2bon_tenant()", "b2bon_escopo()", "b2bon_chave()", "b2bon_visivel(text)"] + [f"{n}(integer)" for n in FUNCOES_DO_PAI]
    return [f"DROP FUNCTION IF EXISTS {nome}" for nome in nomes]


def _nome(prefixo: str, sufixo: str = "") -> str:
    texto = re.sub(r"[^a-z0-9]+", "_", f"{prefixo}_{sufixo}".lower()).strip("_")
    return texto[:60]


def sql_habilitar(tabela: str) -> list[str]:
    return [f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY"]


def sql_tenant_direto(tabela: str, coluna: str = "tenant_id") -> list[str]:
    """Linha só do tenant do contexto (leitura e escrita) e, para a LEITURA, também os tenants que a regra de hierarquia da aplicação ampliou (`app.visiveis`)."""
    return [
        f"CREATE POLICY rls_tenant ON {tabela} FOR ALL USING ({coluna} = b2bon_tenant()) WITH CHECK ({coluna} = b2bon_tenant())",
        f"CREATE POLICY rls_leitura_hierarquia ON {tabela} FOR SELECT USING (b2bon_visivel({coluna}))",
    ]


def sql_duas_partes(tabela: str, colunas: tuple[str, ...]) -> list[str]:
    """Tabela que liga duas empresas por desenho (conexão, mensagem, sala): cada parte enxerga e altera a linha; quem não é parte não vê nada."""
    parte = " OR ".join(f"{c} = b2bon_tenant()" for c in colunas)
    return [f"CREATE POLICY rls_partes ON {tabela} FOR ALL USING ({parte}) WITH CHECK ({parte})"]


def sql_leitura_compartilhada(tabela: str, coluna: str = "tenant_id") -> list[str]:
    """Dado que o produto mostra a outras empresas (diretório, feed): qualquer contexto de tenant lê; só o dono grava."""
    return [
        f"CREATE POLICY rls_leitura_compartilhada ON {tabela} FOR SELECT USING (b2bon_escopo() = 'tenant')",
        f"CREATE POLICY rls_dono_escreve ON {tabela} FOR ALL USING ({coluna} = b2bon_tenant()) WITH CHECK ({coluna} = b2bon_tenant())",
    ]


def sql_herdada(tabela: str, coluna_fk: str, funcao_do_pai: str, *, leitura_compartilhada: bool = False) -> list[str]:
    """Sem `tenant_id` próprio: herda o escopo do pai por uma função que consulta o pai fora do RLS dele."""
    comandos = [f"CREATE POLICY rls_herdada ON {tabela} FOR ALL USING ({funcao_do_pai}({coluna_fk})) WITH CHECK ({funcao_do_pai}({coluna_fk}))"]
    if leitura_compartilhada:
        comandos.append(f"CREATE POLICY rls_leitura_compartilhada ON {tabela} FOR SELECT USING (b2bon_escopo() = 'tenant')")
    return comandos


def sql_busca(escopo: str, tabela: str, predicado: str) -> list[str]:
    """Busca de UMA linha antes de saber o tenant: só leitura, só no escopo nomeado e só a linha cuja chave coincide."""
    return [f"CREATE POLICY {_nome('rls_busca', escopo)} ON {tabela} FOR SELECT USING (b2bon_escopo() = '{escopo}' AND {predicado})"]


def sql_sistema(contexto: str, tabela: str, modo: str) -> list[str]:
    """Tarefa de sistema nomeada: lê (e, se `modo == 'escrever'`, grava) esta tabela inteira, só enquanto o escopo é o dela."""
    nome = _nome("rls_sistema", contexto)
    escopo = f"sistema:{contexto}"
    if modo == "escrever":
        return [f"CREATE POLICY {nome} ON {tabela} FOR ALL USING (b2bon_escopo() = '{escopo}') WITH CHECK (b2bon_escopo() = '{escopo}')"]
    return [f"CREATE POLICY {nome} ON {tabela} FOR SELECT USING (b2bon_escopo() = '{escopo}')"]


def sql_reverter(tabela: str) -> list[str]:
    """Remove toda política `rls_*` da tabela e desliga o RLS (idempotente)."""
    return [
        f"""DO $$ DECLARE p record; BEGIN
  FOR p IN SELECT policyname FROM pg_policies WHERE schemaname = 'public' AND tablename = '{tabela}' AND policyname LIKE 'rls\\_%' LOOP
    EXECUTE format('DROP POLICY %I ON {tabela}', p.policyname);
  END LOOP;
END $$""",
        f"ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY",
    ]


def sql_papel_aplicacao(papel: str, senha: str) -> list[str]:
    """Papel de EXECUÇÃO da aplicação: sem superusuário, sem `BYPASSRLS`, sem DDL, sem `TRUNCATE` (que ignora o RLS) e sem acesso ao controle de versão do Alembic.
    As migrações continuam rodando com o papel dono das tabelas (`MIGRATION_DATABASE_URL`); o RLS vale para quem NÃO é dono (ver docs/b2bon/RLS.md)."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", papel):
        raise ValueError("nome de papel inválido")
    senha_literal = senha.replace("'", "''")
    return [
        f"""DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{papel}') THEN
    CREATE ROLE {papel} LOGIN PASSWORD '{senha_literal}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  ELSE
    ALTER ROLE {papel} LOGIN PASSWORD '{senha_literal}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$""",
        f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {papel}', current_database()); END $$",
        f"GRANT USAGE ON SCHEMA public TO {papel}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {papel}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {papel}",
        f"REVOKE ALL ON alembic_version FROM {papel}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {papel}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {papel}",
    ]
