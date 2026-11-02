# Oficina — Autenticação serverless

Login por CPF e Lambda Authorizer em Python 3.13, com JWT HS256, consulta ao RDS e definição das rotas do API Gateway. O deploy depende de oficina-k8s-infra e oficina-db-infra; o login funcional depende também das migrations da API.

## Responsabilidades deste repositório

- normalizar e validar o CPF e consultar se o cliente está ativo no RDS;
- emitir JWT HS256 e validar tokens no Lambda Authorizer;
- configurar as rotas públicas de login e saúde e as rotas protegidas do Gateway;
- criar o Security Group da Lambda de login e sua regra de acesso ao RDS;
- empacotar os handlers Python com o driver PostgreSQL;
- publicar logs estruturados e habilitar layers Datadog quando a configuração compartilhada estiver disponível.

## Índice da documentação

| Assunto | Documento |
| --- | --- |
| Validação e execução pelo terminal | [Validação local e execução manual](docs/VALIDACAO-E-EXECUCAO-MANUAL.md) |
| Checklist GitHub, dependências, deploy e encerramento | [Execução na AWS](docs/EXECUCAO-AWS.md) |
| Tecnologias, ferramentas, versões e fontes | [Tecnologias e versões](docs/VERSOES.md) |
| Diagnóstico por assunto e recuperação | [Troubleshooting](docs/TROUBLESHOOTING.md) |

## Repositórios da solução

| Repositório | Responsabilidade |
| --- | --- |
| [gestao-oficina-tc-1](https://github.com/tc-organization-26/gestao-oficina-tc-1#readme) | API Java, migrations, Docker Compose e deploy da aplicação |
| [oficina-k8s-infra](https://github.com/tc-organization-26/oficina-k8s-infra#readme) | Bootstrap, rede, EKS, escalabilidade e entrada HTTP |
| [oficina-db-infra](https://github.com/tc-organization-26/oficina-db-infra#readme) | RDS PostgreSQL privado, backups e credencial gerenciada |
| [oficina-auth-lambda](https://github.com/tc-organization-26/oficina-auth-lambda#readme) | Login por CPF, JWT e rotas protegidas do Gateway |

## Dependência obrigatória

Execute primeiro `oficina-k8s-infra` e `oficina-db-infra`, no mesmo ambiente.

Este Terraform lê os seguintes parâmetros do AWS Systems Manager Parameter Store. `ENV` deve ser o mesmo ambiente da rede, do banco e da API:

```text
/oficina/ENV/edge/http-api-id
/oficina/ENV/edge/http-api-execution-arn
/oficina/ENV/edge/app-integration-id
/oficina/ENV/network/vpc-id
/oficina/ENV/network/private-subnet-ids
/oficina/ENV/database/endpoint
/oficina/ENV/database/port
/oficina/ENV/database/name
/oficina/ENV/database/security-group-id
/oficina/ENV/database/master-secret-arn
```

Se esses parâmetros não existirem para o ambiente selecionado, o `terraform plan` falhará antes de criar as funções. O deploy da autenticação pode ocorrer antes da API; o login por CPF depende também do primeiro startup da API com o Flyway concluído.

## Execução e deploy

### Validação local e execução manual

Consulte o [guia de validação local e execução manual](docs/VALIDACAO-E-EXECUCAO-MANUAL.md) para executar testes, montar o pacote e validar o Terraform. Os testes usam Python 3.13 e mocks, sem AWS ou banco real. O pacote deve conter os módulos de `src/` e as dependências de `requirements.txt`.

O Terraform fica em `terraform/` e empacota `../package`. Este repositório não fornece servidor HTTP local; o Compose da aplicação executa o login Java com `login` e `senha`.

### Deploy e execução na AWS

Prepare o [checklist de acessos e configurações](docs/EXECUCAO-AWS.md#checklist-inicial) e conclua as dependências na [ordem de implantação](docs/EXECUCAO-AWS.md#ordem-da-primeira-implantação). Faça o merge para `homologacao` para disparar o deploy em `hom` e aguarde a conclusão. Para produção, use `main` após validar homologação. **Run workflow é uma alternativa ou reexecução**, não um passo obrigatório após o merge.

> O código contém adaptações educacionais de IAM e credenciais. Confira a observação do guia AWS antes de utilizá-lo em outra conta.

Conclua plataforma e RDS no mesmo ambiente. O workflow valida o Python, monta o pacote, aplica Terraform e grava `JWT_SECRET` no Secrets Manager. A API é implantada depois para executar Flyway; só então teste o CPF. Reexecute a autenticação após o primeiro deploy da API para habilitar Datadog com o secret compartilhado.

## Arquitetura

```mermaid
flowchart LR
    cliente["Consumidor da API"] --> gateway["API Gateway · criado em oficina-k8s-infra"]
    subgraph auth["Recursos de oficina-auth-lambda"]
        login["Lambda login · sub-redes privadas"]
        authorizer["Lambda Authorizer · fora da VPC"]
        sg["SG da Lambda e regra de entrada no RDS"]
        jwt["Secrets Manager · chave JWT"]
    end
    gateway -->|POST /auth/login público| login
    login -->|Consulta cliente ativo por CPF| sg
    sg -->|TLS · TCP 5432| rds[("RDS PostgreSQL · oficina-db-infra")]
    login -.->|Lê credencial RDS| credencial["Secrets Manager · secret gerenciado pelo RDS"]
    login -.->|Assina token| jwt
    gateway -->|Autoriza rotas protegidas| authorizer
    authorizer -.->|Valida token| jwt
    authorizer -->|isAuthorized| gateway
    gateway -->|Integração após autorização ou GET health público| api["VPC Link / NLB / Oficina API no EKS"]
    login -.-> obs["Logs JSON / CloudWatch e Datadog quando habilitado"]
    authorizer -.-> obs
```

Consulte os [recursos principais](#recursos-principais) deste componente. A [arquitetura integrada da aplicação](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/ARQUITETURA-SOLUCAO.md) reúne os quatro projetos e suas sequências.

## Arquitetura provisionada

Este repositório configura as rotas de login, saúde e aplicação no Gateway existente. O Authorizer retorna a decisão de acesso; a integração do Gateway encaminha a chamada à API.

## Fluxo de autenticação

O Gateway entrega `POST /auth/login` à Lambda de login, que valida o CPF, consulta o cliente ativo no RDS e emite JWT. Nas chamadas protegidas, a Lambda Authorizer valida o token e devolve a decisão ao Gateway; o Gateway encaminha a requisição pelo VPC Link/NLB à API, que também valida o JWT no Spring Security.

São públicas as rotas `POST /auth/login`, `GET /actuator/health` e `GET /actuator/health/readiness`. As rotas `ANY /` e `ANY /{proxy+}` usam autorização `CUSTOM`, inclusive para Swagger/OpenAPI. Os [diagramas de sequência](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/ARQUITETURA-SOLUCAO.md#sequência-de-autenticação) ficam no documento de arquitetura da solução.

## Recursos principais

| Recurso | Finalidade |
| --- | --- |
| `aws_lambda_function.login` | Valida CPF, consulta o cliente e emite JWT |
| `aws_lambda_function.authorizer` | Valida Bearer JWT no API Gateway |
| `aws_security_group.login_lambda` | Identidade de rede da Lambda de login |
| `aws_vpc_security_group_ingress_rule.database_from_login_lambda` | Libera Lambda → RDS na porta do banco |
| `aws_secretsmanager_secret.auth` | Armazena a chave JWT |
| `aws_apigatewayv2_integration.login` | Integra `POST /auth/login` à Lambda |
| `aws_apigatewayv2_authorizer.jwt` | Protege as rotas da aplicação |
| `archive_file.function` | Empacota handler e driver PostgreSQL |

## Acesso à API

- [Collection Insomnia da autenticação](docs/insomnia/collection.json): configure `BASE_URL`, execute login e copie o token retornado para `TOKEN`.

- [Collection completa da Oficina API](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/src/main/docs/insomnia/collection.yaml): requisições para os demais fluxos, em formato Insomnia.

O Swagger Java descreve o login interno `{login, senha}`; o contrato abaixo descreve o login por CPF atendido pela Lambda na nuvem. Os exemplos HTTP podem ser reproduzidos no Insomnia; o [guia AWS](docs/EXECUCAO-AWS.md#validar-as-funções-e-o-login) traz o teste em PowerShell.

### Login

```http
POST /auth/login
Content-Type: application/json
```

O CPF pode ser enviado somente com dígitos ou com pontuação. O login por CPF é uma demonstração e não comprova posse de senha ou segundo fator. A API oferece cadastro de clientes; o exemplo abaixo usa o cliente fictício criado pelo Flyway para testes e demonstrações:

```json
{
  "cpf": "003.619.370-40"
}
```

Resposta de sucesso:

```json
{
  "token": "eyJ..."
}
```

| Status | Situação |
| --- | --- |
| `200` | CPF válido, cliente existente e ativo; JWT emitido |
| `400` | Corpo inválido ou CPF com formato/dígitos verificadores inválidos |
| `403` | Cliente encontrado, porém inativo |
| `404` | Nenhum cliente encontrado para o CPF |
| `500` | Falha inesperada ao consultar dependências |

### Chamada protegida

```http
GET /clientes
Authorization: Bearer eyJ...
```

Token ausente, adulterado ou expirado é recusado pelo Lambda Authorizer.

## Estrutura do repositório

| Arquivo ou diretório | Responsabilidade |
| --- | --- |
| [src/handler.py](src/handler.py) | Login CPF, consulta PostgreSQL, emissão e validação de JWT |
| [src/observability.py](src/observability.py) | Logs estruturados, duração e observação das integrações |
| [requirements.txt](requirements.txt) | Dependências Python empacotadas com os handlers |
| [tests/](tests) | Testes unitários de autenticação e observabilidade |
| [terraform/main.tf](terraform/main.tf) | Funções, pacote ZIP, rede, secret JWT e rotas/Authorizer |
| [terraform/datadog.tf](terraform/datadog.tf) | Layers e instrumentação das Lambdas |
| [terraform/variables.tf](terraform/variables.tf), [versions.tf](terraform/versions.tf) e [outputs.tf](terraform/outputs.tf) | Entradas, providers e saídas do Terraform |
| [.github/workflows/cicd.yml](.github/workflows/cicd.yml) | Testes, pacote, deploy, atualização do secret e promoção |
| [docs/insomnia/collection.json](docs/insomnia/collection.json) | Readiness, login e chamada protegida |

## JWT

O token é assinado com HMAC SHA-256 (`HS256`) e possui validade padrão de 3600 segundos.

| Claim | Conteúdo |
| --- | --- |
| `sub` | UUID do cliente retornado pelo banco |
| `papel` | `CLIENTE` |
| `iat` | Instante de emissão |
| `exp` | Instante de expiração |

O mesmo `JWT_SECRET` é entregue à aplicação no EKS, permitindo que o Spring Security valide o token depois da autorização no Gateway.

## Consulta ao banco

A Lambda executa uma consulta parametrizada equivalente a:

```sql
SELECT id, ativo
FROM cliente
WHERE cpf_cnpj = ?;
```

O acesso usa `pg8000`, um driver PostgreSQL Python empacotado junto da função. As credenciais não ficam no código nem no state deste repositório: são lidas do secret gerenciado pelo RDS.

O CPF é armazenado sem pontuação. A identificação do [cliente inicial de teste](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/ARQUITETURA-SOLUCAO.md#contratos-segurança-e-persistência) fica documentada junto das migrations da API. O login só funciona depois do primeiro startup da API com o Flyway concluído.

## Rede e segurança

O Terraform:

- coloca a Lambda de login nas sub-redes privadas da VPC;
- cria um security group exclusivo para a Lambda;
- libera no security group do RDS somente tráfego TCP da Lambda para a porta publicada pelo banco, normalmente `5432`;
- mantém o RDS privado;
- utiliza conexão TLS com o PostgreSQL;
- mantém a Lambda Authorizer fora da VPC, pois ela precisa somente validar o JWT e acessar o Secrets Manager.

As sub-redes privadas precisam de saída para o Secrets Manager. A infraestrutura Kubernetes habilita NAT Gateway por padrão através de `enable_nat_gateway = true`.

No ambiente educacional, as funções reutilizam a `LabRole`. Ela precisa permitir criação e remoção de interfaces de rede da Lambda, leitura dos parâmetros SSM e leitura dos secrets utilizados.

## Configuração Terraform e descoberta

As variáveis são declaradas em [variables.tf](terraform/variables.tf) e [datadog.tf](terraform/datadog.tf).

| Variável | Padrão | Uso |
| --- | --- | --- |
| `aws_region` | `us-east-1` | Região dos recursos |
| `project_name` | `oficina` | Prefixo de nomes e caminhos SSM |
| `environment` | `dev` | Informe `hom` ou `prod` ao integrar com o CI/CD |
| `lab_role_arn` | Obrigatória, sem padrão | Role preexistente das funções |
| `jwt_expiration_seconds` | `3600` | Validade do JWT em segundos |
| `database_connect_timeout_seconds` | `5` | Timeout da conexão PostgreSQL em segundos |
| `datadog_enabled` | `false` | Ativa instrumentação nas duas funções |
| `datadog_site` | `datadoghq.com` | Site da conta Datadog |
| `datadog_version` | `local` | Versão de telemetria; no Actions recebe o SHA |
| `datadog_python_layer_version` | `127` | Layer Python 3.13 |
| `datadog_extension_layer_version` | `99` | Layer da extensão Datadog |
| `datadog_api_key_secret_arn` | Vazio | Obrigatório quando Datadog estiver habilitado |

Os [outputs](terraform/outputs.tf) são `login_function_name`, `authorizer_function_name`, `auth_secret_arn` e `login_lambda_security_group_id`. O secret `oficina-ENV/auth` contém somente `jwtSecret`; o workflow grava o valor após o apply. `AUTH_LOGIN`, `AUTH_PASSWORD` e `ADMIN_ID` não são utilizados.

A autenticação usa `oficina/auth/hom.tfstate` ou `oficina/auth/prod.tfstate`. Use o mesmo ambiente da plataforma, do banco e da aplicação.

## Validação após o deploy

Confirme que as funções estão ativas, aguarde o Flyway da API e siga o [teste de login e rota protegida](docs/EXECUCAO-AWS.md#validar-as-funções-e-o-login). O CPF fictício `003.619.370-40` deve retornar JWT após o seed; uma chamada sem token a `/clientes` deve ser recusada.

Os outputs são `login_function_name`, `authorizer_function_name`, `auth_secret_arn` e `login_lambda_security_group_id`. Falhas de CPF, rede, secrets e Authorizer estão divididas por assunto no [troubleshooting](docs/TROUBLESHOOTING.md).

## Observabilidade

Os handlers emitem logs JSON com identificador, duração e resultado, além de `dd.trace_id`/`dd.span_id` quando o tracer está ativo. O login devolve `X-Request-ID`; CPF, JWT, senhas e corpo da requisição não são registrados. Falhas PostgreSQL/Secrets Manager geram `integration.failed` e respostas 500 marcam o trace como erro.

A esteira descobre o secret `oficina-ENV/datadog`, alimentado pela API, e habilita as layers `Datadog-Python313:127` e `Datadog-Extension:99` (x86_64). Se o secret ainda não existir, publica sem tracer e emite um aviso; após o deploy da API, reexecute a Lambda. A `LabRole` precisa ler o secret e acessar as layers; o login precisa de saída HTTPS pelo NAT. A variável opcional `DD_SITE` deve corresponder à conta usada pela API.

Não é necessário duplicar `DD_API_KEY`/`DD_APP_KEY` neste repositório. A configuração compartilhada, dashboards, monitores e limites de correlação estão no [guia Datadog da API](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/OBSERVABILIDADE.md). Para consultar as funções, filtre `env:hom (service:oficina-login OR service:oficina-authorizer)`.

## Encerramento

Remova a API antes da autenticação e este componente antes do RDS/Gateway, seguindo o [encerramento](docs/EXECUCAO-AWS.md#encerramento). A exclusão do secret JWT não tem janela de recuperação no código atual. Uma recriação precisa publicar a chave e atualizar os consumidores consistentemente.

## Workflow

- [Workflow deste componente](.github/workflows/cicd.yml).
- [Histórico de execuções](https://github.com/tc-organization-26/oficina-auth-lambda/actions/workflows/cicd.yml).

### Fluxo de branches

`fase-3` valida e abre PR para `homologacao`; `homologacao` faz deploy em `hom` e abre PR para `main`; `main` faz deploy em `prod`. Os merges são manuais. Executar manualmente em `fase-3` também só valida. Consulte [branches e ambientes](docs/EXECUCAO-AWS.md#branches-e-ambientes).

## Troubleshooting

Consulte o [guia de diagnóstico deste componente](docs/TROUBLESHOOTING.md) para sintomas, comandos de verificação e correções por assunto. O guia também referencia os demais componentes quando a falha atravessa rede, banco, autenticação ou aplicação.
