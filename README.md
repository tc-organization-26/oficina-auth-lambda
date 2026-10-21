# Oficina — Lambda de Autenticação

Componente serverless responsável pela autenticação externa da plataforma Oficina. Este repositório implementa a função de login, a emissão de JWT e o Lambda Authorizer usado pelo Amazon API Gateway para proteger o acesso à aplicação no EKS.

> Para o ambiente educacional, consulte [Execução no AWS Lab](docs/EXECUCAO-LAB.md). As Lambdas reutilizam a `LabRole`, pois o Lab bloqueia a criação de roles IAM próprias.

## Links de deploy e documentação da API

- [Deployments ativos](https://github.com/tc-organization-26/oficina-auth-lambda/deployments): cada execução bem-sucedida registra a URL real do API Gateway do ambiente.
- [Pipeline CI/CD](https://github.com/tc-organization-26/oficina-auth-lambda/actions/workflows/cicd.yml).
- Endpoint publicado: abra o deployment ativo e acrescente `/auth/login` à URL exibida.
- Swagger/OpenAPI da plataforma: consulte a [documentação da Oficina API](https://github.com/tc-organization-26/gestao-oficina-tc-1#links-de-deploy-e-documentação-da-api). A Lambda possui somente o contrato de login documentado neste README e não mantém um Swagger separado.

## Tecnologias utilizadas

- Python 3.13 e biblioteca padrão;
- AWS Lambda e Lambda Authorizer;
- Amazon API Gateway HTTP API;
- AWS Secrets Manager, IAM e CloudWatch Logs;
- Terraform;
- GitHub Actions com credenciais temporárias do AWS Lab.

## Dockerfile

Não se aplica. As funções são empacotadas como arquivo ZIP pelo provider `archive` do Terraform e executadas no runtime gerenciado do AWS Lambda, sem imagem de contêiner.

## Responsabilidades deste repositório

- empacotar o código Python das funções;
- criar a Lambda de login;
- criar a Lambda Authorizer;
- criar a role de execução e as permissões mínimas das funções;
- criar o secret de autenticação no AWS Secrets Manager;
- integrar a rota pública `POST /auth/login` ao API Gateway;
- proteger as demais rotas com o authorizer;
- popular o secret de autenticação a partir dos secrets do GitHub Actions.

Este repositório não cria o API Gateway, o EKS ou o banco. Esses componentes pertencem aos repositórios de infraestrutura.

## Fluxo de autenticação

```text
POST /auth/login
  -> API Gateway
     -> Lambda login
        -> Secrets Manager
        -> valida login e senha
        -> gera JWT HS256

Authorization: Bearer JWT
  -> API Gateway
     -> Lambda Authorizer
        -> valida assinatura e expiração
        -> libera ou bloqueia a chamada
     -> integração privada da aplicação no EKS
```

A rota de login é pública. As rotas `ANY /` e `ANY /{proxy+}` usam autorização `CUSTOM` e encaminham chamadas autorizadas para a integração da aplicação.

## Implementação

O arquivo `src/handler.py` expõe dois handlers:

- `handler.login`: autentica e retorna o JWT;
- `handler.authorizer`: valida o Bearer token e retorna uma resposta simples do API Gateway.

As funções usam:

- runtime Python 3.13;
- JWT assinado com HMAC SHA-256 (`HS256`);
- segredo lido do Secrets Manager e mantido em cache durante o ciclo de vida do runtime;
- tempo de expiração configurável, com padrão de 3600 segundos.

### Claims do JWT

| Claim | Conteúdo |
| --- | --- |
| `sub` | Identificador do usuário administrativo |
| `papel` | `ADMINISTRADOR` |
| `iat` | Instante de emissão |
| `exp` | Instante de expiração |

O contexto enviado pelo authorizer contém `subject` e `role`.

## Contrato da API

### Login

```http
POST /auth/login
Content-Type: application/json
```

```json
{
  "login": "admin",
  "senha": "senha-configurada"
}
```

Resposta de sucesso:

```json
{
  "token": "eyJ..."
}
```

Respostas possíveis:

| Status | Situação |
| --- | --- |
| `200` | Credenciais válidas |
| `401` | Login ou senha inválidos |
| `400` | JSON inválido ou configuração incompleta |

### Chamada protegida

```http
GET /clientes
Authorization: Bearer eyJ...
```

Token ausente, assinatura incorreta ou token expirado resulta em `isAuthorized: false` no authorizer.

## Secret de autenticação

O Terraform cria um secret chamado:

```text
oficina-ENV/auth
```

Conteúdo esperado:

```json
{
  "adminLogin": "admin",
  "adminPassword": "senha-segura",
  "jwtSecret": "chave-de-assinatura-com-32-bytes-ou-mais",
  "adminId": "00000000-0000-0000-0000-000000000001"
}
```

O workflow grava uma nova versão do secret após o `terraform apply`. O conteúdo não é armazenado no state Terraform nem no código-fonte.

## Dependências

Execute primeiro `oficina-k8s-infra`. Este Terraform consulta:

```text
/oficina/ENV/edge/http-api-id
/oficina/ENV/edge/http-api-execution-arn
/oficina/ENV/edge/app-integration-id
```

Esses parâmetros identificam o API Gateway já existente e a integração privada que aponta para a aplicação no EKS.

O repositório de banco não é uma dependência direta desta implementação.

## Recursos Terraform

| Recurso | Finalidade |
| --- | --- |
| `archive_file` | Gera `function.zip` a partir de `src/handler.py` |
| `aws_secretsmanager_secret` | Armazena credenciais e chave JWT |
| `aws_iam_role` | Role das funções Lambda |
| `aws_iam_role_policy_attachment` | Permissão de logs no CloudWatch |
| `aws_iam_role_policy` | Leitura exclusiva do secret de autenticação |
| `aws_lambda_function.login` | Endpoint de login |
| `aws_lambda_function.authorizer` | Autorizador do API Gateway |
| `aws_apigatewayv2_integration` | Integra o login à Lambda |
| `aws_apigatewayv2_authorizer` | Registra o REQUEST authorizer |
| `aws_apigatewayv2_route` | Cria a rota pública e protege as demais |
| `aws_lambda_permission` | Permite invocação pelo API Gateway |

## Variáveis Terraform

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `aws_region` | `us-east-1` | Região AWS |
| `project_name` | `oficina` | Prefixo dos recursos e caminhos SSM |
| `environment` | `dev` | Ambiente atual |
| `jwt_expiration_seconds` | `3600` | Validade do token em segundos |

## Outputs

- `login_function_name`
- `authorizer_function_name`
- `auth_secret_arn`

## Testes locais

Os testes não acessam a AWS. Eles verificam geração, leitura e rejeição de JWT com assinatura inválida.

```powershell
python -m unittest discover -s tests
```

## Validação local do Terraform

```powershell
Set-Location terraform
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

O arquivo `terraform/function.zip` é gerado pelo provider Archive e não deve ser versionado.

## Aplicação manual

Exemplo para homologação:

```powershell
$env:TF_VAR_environment = "hom"
$env:TF_VAR_aws_region = "us-east-1"

Set-Location terraform
terraform init `
  -backend-config="bucket=SEU_BUCKET" `
  -backend-config="key=oficina/auth/hom.tfstate" `
  -backend-config="region=us-east-1" `
  -backend-config="encrypt=true" `
  -backend-config="use_lockfile=true"

terraform plan
terraform apply
```

Depois do apply, grave o conteúdo esperado no secret `oficina-hom/auth` antes de chamar a rota de login.

## CI/CD

O workflow `.github/workflows/cicd.yml` possui dois jobs.

### `testar`

1. configura Python 3.13;
2. executa os testes unitários;
3. configura Terraform;
4. executa `fmt`, `init -backend=false` e `validate`.

### `deploy`

1. carrega as credenciais temporárias do AWS Lab;
2. inicializa o backend S3 do ambiente;
3. executa `terraform apply`;
4. atualiza o secret de autenticação com os secrets do GitHub.

Mapeamento de ambientes:

| Branch | Ambiente | Chave do state |
| --- | --- | --- |
| `homologacao` | `hom` | `oficina/auth/hom.tfstate` |
| `main` ou `master` | `prod` | `oficina/auth/prod.tfstate` |

### Variables do GitHub

Normalmente configuradas pelo bootstrap:

- `LAB_ROLE_ARN`
- `AWS_REGION`
- `TF_STATE_BUCKET`

Organization secrets esperados:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`

### Secrets do GitHub

| Secret | Uso |
| --- | --- |
| `AUTH_LOGIN` | Login administrativo |
| `AUTH_PASSWORD` | Senha administrativa |
| `JWT_SECRET` | Assinatura dos tokens; use pelo menos 32 bytes aleatórios |
| `ADMIN_ID` | Identificador enviado no claim `sub` |

Use valores diferentes por GitHub Environment quando separar homologação e produção.

## Verificação após o deploy

Obtenha a URL pelo repositório Kubernetes:

```powershell
aws ssm get-parameter `
  --name /oficina/hom/edge/http-api-id
```

Ou use o output `api_gateway_url` de `oficina-k8s-infra`. Depois:

```powershell
$body = @{ login = "admin"; senha = "senha-configurada" } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "https://API_ID.execute-api.us-east-1.amazonaws.com/auth/login" `
  -ContentType "application/json" `
  -Body $body
```

Também é possível conferir as funções:

```powershell
aws lambda get-function --function-name oficina-hom-login
aws lambda get-function --function-name oficina-hom-authorizer
```

## Estrutura

```text
.
├── .github/workflows/cicd.yml
├── src/handler.py
├── tests/test_handler.py
└── terraform/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    └── versions.tf
```
