# Autenticação serverless no AWS Lab

Este repositório é executado depois da infraestrutura EKS/API Gateway e do RDS, e antes do deploy da aplicação.

## Arquitetura

```text
POST /auth/login
    -> API Gateway
    -> Lambda login nas sub-redes privadas
    -> valida CPF
    -> consulta id e ativo no RDS
    -> JWT HS256 com papel CLIENTE

Demais rotas
    -> API Gateway
    -> Lambda Authorizer
    -> VPC Link / NLB
    -> Oficina API no EKS
```

As duas funções usam a `LabRole` preexistente. O Terraform não cria role nem policy IAM, atendendo às restrições do AWS Academy/Vocareum.

## Configuração GitHub

Organization secrets compartilhados com os quatro repositórios:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
```

Repository secrets específicos deste repositório:

```text
JWT_SECRET
```

`JWT_SECRET` deve conter pelo menos 32 bytes aleatórios. Credenciais administrativas antigas não são mais usadas pelo login serverless.

Variables configuradas pelo bootstrap:

```text
AWS_REGION
TF_STATE_BUCKET
LAB_ROLE_ARN
```

## Promoção automática entre branches

O workflow usa o `GITHUB_TOKEN` fornecido automaticamente pelo GitHub. Em **Settings → Actions → General → Workflow permissions**, selecione **Read and write permissions** e habilite **Allow GitHub Actions to create and approve pull requests**. Não é necessário cadastrar outro secret.

O fluxo de promoção é:

```text
push em fase-3
  -> abre ou atualiza PR de fase-3 para homologacao
  -> merge manual após os checks
  -> abre ou atualiza PR de homologacao para main
  -> merge manual após os checks
```

Se `homologacao` ainda não existir, o workflow a cria a partir de `main`. Proteja `homologacao` e `main` contra push direto e exija Pull Request para merge.

## Pré-requisitos

Antes desta etapa, confirme:

1. `oficina-k8s-infra/terraform.yml` concluído;
2. `oficina-db-infra/terraform.yml` concluído;
3. parâmetros `/oficina/hom/edge/*` existentes no SSM;
4. cliente `00361937040` cadastrado e ativo pela migration da aplicação;
5. credenciais temporárias ainda válidas.

## Execução

Pelo GitHub: **Actions → CI/CD - Lambda de Autenticacao → Run workflow**, selecionando `fase-3`.

Pelo terminal:

```powershell
gh workflow run cicd.yml `
  --repo tc-organization-26/oficina-auth-lambda `
  --ref fase-3

gh run list `
  --repo tc-organization-26/oficina-auth-lambda `
  --workflow cicd.yml `
  --limit 3

gh run watch ID `
  --repo tc-organization-26/oficina-auth-lambda `
  --exit-status
```

O workflow testa o Python, valida o Terraform, empacota o driver PostgreSQL, cria o secret JWT, publica as funções e configura a integração, o authorizer e as rotas.

## State e ambientes

```text
fase-3 ou homologacao -> ambiente hom
main                  -> ambiente prod
```

States:

```text
s3://TF_STATE_BUCKET/oficina/auth/hom.tfstate
s3://TF_STATE_BUCKET/oficina/auth/prod.tfstate
```

## Validação

```powershell
aws lambda get-function `
  --function-name oficina-hom-login `
  --query "Configuration.{Nome:FunctionName,Runtime:Runtime,Estado:State,Role:Role}" `
  --output table

aws lambda get-function `
  --function-name oficina-hom-authorizer `
  --query "Configuration.{Nome:FunctionName,Runtime:Runtime,Estado:State,Role:Role}" `
  --output table
```

As duas funções devem mostrar a `LabRole`. Para testar o login:

```powershell
$apiId = aws ssm get-parameter `
  --name /oficina/hom/edge/http-api-id `
  --query Parameter.Value `
  --output text

$url = "https://$apiId.execute-api.us-east-1.amazonaws.com"

Invoke-RestMethod `
  -Method Post `
  -Uri "$url/auth/login" `
  -ContentType application/json `
  -Body (@{ cpf = "003.619.370-40" } | ConvertTo-Json)
```

Não publique o JWT ou o conteúdo do Secrets Manager nos logs.
