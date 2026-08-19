# API de provisionamento/billing pra Distribuidores

Fase 2 da hierarquia de tenants (Distribuidor → Revendedor → Cliente).
Pensada pro **sistema do próprio Distribuidor** (ERP, billing interno etc.)
chamar o B2B ON de fora do painel — sem humano logado.

Só tenants `tipo="distribuidor"` podem gerar chave de API. Revendedor
continua gerenciando sua árvore só pelo painel (login normal).

## Autenticação

1. Logue no painel como admin do seu tenant Distribuidor.
2. Vá em **Integrações** (menu lateral) → **Gerar chave**.
3. Copie a chave completa na hora — ela não aparece de novo, o B2B ON só
   guarda o hash. Se perder, gere outra e revogue a antiga.
4. Toda chamada em `/api/v1/parceiros/*` leva:

```
Authorization: Bearer b2bon_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Chave inválida ou revogada → `401`. Tenant fora da sua árvore → `403`.
Limite de 100 requisições/minuto por chave (`429` acima disso).

## Endpoints

### `POST /api/v1/parceiros/tenants` — provisionar Revendedor

Cria um Revendedor novo direto sob o seu Distribuidor, com o primeiro
usuário (`admin`) já pronto pra logar.

```json
{
  "tenant_id": "revenda-acme",
  "razao_social": "Acme Revenda Ltda",
  "cnpj": "11222333000181",
  "plano_id": 2,
  "nome_admin": "Fulano de Tal",
  "email_admin": "fulano@acmerevenda.com.br",
  "senha_admin": "senha-forte-aqui"
}
```

Resposta `201`: o `Tenant` criado (`id`, `tipo="revendedor"`, `tenant_pai_id`,
`modo_cobranca`).

### `GET /api/v1/parceiros/tenants` — sua subárvore

Lista você mesmo + todos os Revendedores/Clientes abaixo de você.

### `PUT /api/v1/parceiros/tenants/{tenant_id}/licenca` — plano/status

```json
{ "plano_id": 3, "status": "ativa", "data_expiracao": "2026-12-31T00:00:00Z" }
```

Todos os campos opcionais (manda só o que quer mudar). `tenant_id` precisa
estar na sua árvore, senão `403`.

### `GET /api/v1/parceiros/tenants/{tenant_id}/uso` — consumo do mês

```json
{ "limite": 200, "usado": 87, "restante": 113 }
```

### `GET /api/v1/parceiros/tenants/{tenant_id}/billing` — status de pagamento

```json
{ "id": 42, "tenant_id": "revenda-acme", "plano_id": 2, "status": "ativa", "data_inicio": "...", "data_expiracao": "..." }
```

## Webhooks

Configurados na mesma tela **Integrações**: uma URL de callback por
Distribuidor. A cada evento, o B2B ON faz:

```
POST <sua_url_callback>
Content-Type: application/json
X-B2BON-Signature: sha256=<hmac hex>
```

`X-B2BON-Signature` é HMAC-SHA256 do corpo bruto da requisição, com o
segredo mostrado uma vez na tela (ao criar/atualizar o webhook). Verificação
(exemplo Python):

```python
import hashlib
import hmac

def valido(segredo: str, corpo_bruto: bytes, header_assinatura: str) -> bool:
    esperado = "sha256=" + hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, header_assinatura)
```

Entrega tem retentativa com backoff (1min, 5min, 15min, 1h, 6h — até 6
tentativas) se sua URL não responder `2xx`; depois disso, desiste (sem
alerta automático ainda — acompanhe pelo `GET /api/v1/parceiros/tenants/...`
se suspeitar que perdeu algum evento).

### Eventos

| `tipo_evento` | Quando dispara | Payload |
|---|---|---|
| `tenant_provisionado` | Um Revendedor/Cliente novo nasceu na sua árvore (painel ou API) | `{tenant_id, razao_social, tipo, tenant_pai_id, plano_id}` |
| `licenca_suspensa` | Licença suspensa automaticamente por inadimplência | `{tenant_id, data_expiracao}` |
| `licenca_atualizada` | Plano ou status de licença mudou | `{tenant_id, plano_id, status}` |
| `pagamento_confirmado` | Pagamento (Mercado Pago) aprovado | `{tenant_id, plano_id, valor}` |
