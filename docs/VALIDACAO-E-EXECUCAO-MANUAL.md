# Validação local e execução manual na AWS — oficina-auth-lambda

[README](../README.md) · [Troubleshooting](TROUBLESHOOTING.md) · [AWS](EXECUCAO-LAB-AWS.md)

Para preparar o computador, consulte a [instalação das ferramentas](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/INSTALACAO-FERRAMENTAS.md). Para executar fora do Academy/Vocareum, siga a [preparação de conta AWS comum](https://github.com/tc-organization-26/oficina-k8s-infra/blob/HEAD/docs/CONTA-AWS-COMUM.md), incluindo as adaptações de IAM, Terraform e workflows.

Pré-requisitos: Git e Terraform >= 1.10 (as esteiras fixam 1.15.9). Use Python 3.13 para testes e empacotamento.

## Testes Python

Com Python 3.13, na raiz do repositório:

```powershell
python -m unittest discover -s tests
```

Os testes usam mocks e não acessam AWS ou banco real. Este repositório não fornece servidor HTTP/Compose para executar a Lambda localmente. Para usar toda a API no computador, utilize o [Compose de `gestao-oficina-tc-1`](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/HEAD/docs/EXECUCAO-LOCAL.md); seu login local é Java com `{login, senha}`.

## Empacotamento

Monte o pacote antes da validação e de cada plano que deva incluir alterações Python:

```powershell
New-Item -ItemType Directory -Force package | Out-Null
python -m pip install --requirement requirements.txt --target package
Copy-Item src/*.py package/ -Force
python -c "import sys; sys.path.insert(0, 'package'); import pg8000.dbapi, scramp; assert callable(scramp.make_channel_binding)"
Set-Location terraform
```

O runtime Lambda fornece `boto3`; o pacote inclui o driver e os módulos em `src`. Se mudar versões de dependências, use um diretório `package` limpo para evitar arquivos de versões anteriores. Os comandos Terraform abaixo são executados em `terraform/`.

## Validação sem credenciais AWS

A validação não exige conta AWS. O `init` baixa providers/módulos e precisa de internet se eles ainda não estiverem no cache.

```powershell
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

> **Observação:** os comandos AWS abaixo seguem a configuração atual do projeto. Confira as [adaptações educacionais e os pré-requisitos de IAM](EXECUCAO-LAB-AWS.md) antes de utilizá-los em outra conta.

## Credenciais para comandos locais que acessam a AWS

`plan`, `apply` e comandos `aws` acessam a conta real; a aplicação dos planos pode criar recursos cobrados. As credenciais do GitHub não configuram automaticamente o seu terminal.

Copie as credenciais da sessão AWS para as variáveis do terminal, sem salvá-las no repositório:

```powershell
$env:AWS_ACCESS_KEY_ID = "ACCESS_KEY_DA_SESSAO"
$env:AWS_SECRET_ACCESS_KEY = "SECRET_KEY_DA_SESSAO"
$env:AWS_SESSION_TOKEN = "SESSION_TOKEN_DA_SESSAO"
$env:AWS_DEFAULT_REGION = "us-east-1"
aws sts get-caller-identity
```

Confira a conta antes do plano. Use o mesmo `project_name`, ambiente, região, bucket e chave de state usados pelo CI/CD; o padrão Terraform `environment=dev` não equivale a `hom`. Não use um state novo para recursos que já estão gerenciados por outro state.

## Aplicação manual na AWS

Execute primeiro bootstrap, rede/EKS e RDS no mesmo ambiente. O plano consulta parâmetros SSM da rede, do banco e do Gateway.

Informe o bucket real criado pelo bootstrap, sem copiar literalmente `SEU_BUCKET` ou `ACCOUNT_ID`. Execute na pasta `terraform/` após o empacotamento. A chave identifica o mesmo state usado pela esteira:

```powershell
$env:TF_VAR_environment = "hom"
$env:TF_VAR_aws_region = "us-east-1"
$env:TF_VAR_lab_role_arn = "arn:aws:iam::ACCOUNT_ID:role/LabRole"

terraform init -reconfigure `
  -backend-config="bucket=SEU_BUCKET" `
  -backend-config="key=oficina/auth/hom.tfstate" `
  -backend-config="region=us-east-1" `
  -backend-config="encrypt=true" `
  -backend-config="use_lockfile=true"

terraform plan -lock-timeout=5m -out=tfplan
```

Revise o plano, confira se não há outra execução ativa e aplique o plano salvo:

```powershell
terraform apply -lock-timeout=5m tfplan
terraform output
```

O apply manual cria o secret `oficina-hom/auth`, mas não grava seu conteúdo. No Secrets Manager, adicione uma versão JSON com `jwtSecret` e a mesma chave de pelo menos 32 bytes configurada em `JWT_SECRET` no GitHub. Faça isso antes de implantar a API ou testar login. A atualização automática desse valor pertence ao workflow, não ao Terraform.

O Datadog é desabilitado por padrão no Terraform local. Para habilitá-lo após a API publicar o secret compartilhado, defina `TF_VAR_datadog_enabled=true`, `TF_VAR_datadog_api_key_secret_arn` com o ARN de `oficina-hom/datadog` e `TF_VAR_datadog_site` correspondente à conta antes do plano.

Para produção, altere tanto `TF_VAR_environment` quanto a chave do backend para `prod`. Não aplique manualmente em paralelo ao Actions. Não versione credenciais, `terraform.tfvars`, pacote, planos ou state; esses arquivos podem conter informações sensíveis. Consulte a [validação e o encerramento na AWS](EXECUCAO-LAB-AWS.md).
