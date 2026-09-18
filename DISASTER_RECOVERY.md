# Disaster Recovery — o que já existe hoje

Este documento registra a estratégia REAL de backup/restore em uso
(Fase 7D, hardening) — não introduz nenhuma automação nova. Objetivo:
não perguntar de novo/redescobrir isso numa emergência real.

## Banco de dados (Neon Postgres)

O Neon gerencia backup/point-in-time recovery (PITR) automaticamente
— não existe (e não é preciso existir) nenhum script de `pg_dump`
agendado neste repositório nem em `.github/workflows/`.

- **Onde confirmar a janela de retenção atual**: painel Neon → projeto
  `b2bon` → **Backup/Restore** (ou **Settings**) — a janela depende do
  plano em uso no momento e pode ter mudado desde a última verificação
  aqui registrada; não assuma um número fixo sem confirmar ali.
- **Restore já testado de verdade** (2026-08-19, ver memória
  `project_raio_x_infra_checklist`): criado um branch (`teste-restore`)
  a partir de um ponto no tempo passado do branch `production` — a
  contagem da tabela `conta` bateu 87/87 entre `production` e
  `teste-restore`, confirmando que o restore point-in-time funciona de
  ponta a ponta neste projeto. O branch de teste tinha auto-delete em
  1 dia.
- **Como restaurar de verdade numa emergência**: Neon → projeto `b2bon`
  → **Branches** → **Restore** (ou criar um branch novo a partir de um
  ponto no tempo, como no teste acima) → apontar `DATABASE_URL` do
  Render pro branch restaurado (ou promovê-lo a `production`, conforme
  a op ção que o painel Neon oferecer no momento).
- **Staging usa um branch COPY-ON-WRITE de produção** (ver
  `STAGING.md`) — não é um backup independente; um problema na branch
  raiz de produção também afeta o que o staging herdou dela até aquele
  ponto.

## O que NÃO está coberto por este plano

- **Credenciais de canal por tenant** (WhatsApp/e-mail — cifradas com
  `CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY`): se essa chave de
  criptografia for perdida, as credenciais já cifradas no banco ficam
  permanentemente ilegíveis — o Neon restaura os BYTES, não decifra
  nada. A chave em si precisa da própria estratégia de backup do
  gerenciador de segredos do Render (fora do escopo deste documento).
- **Configuração do Cloudflare Worker** (frontend) — vive no painel da
  Cloudflare, não no banco; recriar do zero segue o mesmo passo a
  passo de `STAGING.md` (Passo 4), sem backup automático dedicado.
- **Estado dos provedores externos** (WhatsApp Business/Meta, SendGrid,
  Mercado Pago) — nenhum desses guarda histórico "restaurável" pelo
  nosso lado; um problema neles se resolve direto no painel de cada
  provedor.
- **Neo4j** — instância AuraDB Free já foi deletada por inatividade
  antes (ver memória `project_neo4j_aura_pausada_grafo_pendente`); o
  sistema já trata Neo4j indisponível sem quebrar nada, então isso não
  é tratado como incidente de DR.

## Objetivo de tempo de recuperação (RTO/RPO) — honesto, não aspiracional

Nenhum RTO/RPO formal foi definido ou testado sob carga real — o único
dado real disponível é o teste de restore de 2026-08-19 (bem-sucedido,
tempo de execução não cronometrado). Definir um RTO/RPO com número
específico exigiria um novo teste cronometrado deliberado, que não
faz parte desta entrega.
