# Tecnologias e versões — oficina-auth-lambda

[README](../README.md) · [Validação local e execução manual](VALIDACAO-E-EXECUCAO-MANUAL.md) · [Execução no laboratório AWS](EXECUCAO-LAB-AWS.md)

| Tecnologia | Versão / referência | Uso |
| --- | --- | --- |
| Python / runtime Lambda | 3.13 / `python3.13` | Handlers e testes |
| pg8000 / scramp | 1.31.2 / 1.4.18 | Acesso PostgreSQL e autenticação do driver |
| boto3 | Fornecida pelo runtime Lambda | Sem pin próprio em requirements.txt |
| JWT | HS256 | Algoritmo de assinatura; não é versão de biblioteca |
| Terraform | 1.15.9 no CI; mínimo 1.10.0 | Provisionamento |
| Providers AWS / Archive | 6.69.1 / 2.8.1 no lock | Constraints `~> 6.0` / `~> 2.7` |
| Layers Datadog Python / Extension | 127 / 99 por padrão | APM e logs nas Lambdas |
| AWS CLI / Insomnia | 2.36.34 / 13.1.0 | Ferramentas de referência |
| Lambda, API Gateway HTTP API, Secrets Manager, SSM, S3 e CloudWatch | Serviços gerenciados | Execução, autenticação, configuração e logs |
| GitHub Actions | Serviço gerenciado | Versões das actions no workflow |

As versões fixadas no código e nos lockfiles prevalecem. As tabelas distinguem versões fixadas, faixas aceitas, valores padrão e ferramentas de referência.

## Fontes das versões

- [requirements.txt](../requirements.txt): versões fixadas de pg8000 e scramp.
- [main.tf](../terraform/main.tf) e [workflow](../.github/workflows/cicd.yml): runtime Python, Terraform e versão Python dos testes.
- [versions.tf](../terraform/versions.tf) e [lockfile](../terraform/.terraform.lock.hcl): constraints e resolução dos providers.
- [datadog.tf](../terraform/datadog.tf): versões padrão das layers.

O boto3 é importado do runtime da Lambda, sem versão própria fixada no pacote. As layers Datadog possuem versões numéricas de publicação (`127` e `99`), distintas da versão do Python (`3.13`).

Uma versão no lockfile identifica a resolução versionada; a constraint no Terraform define a faixa aceita. Uma versão major de imagem ou runtime não fixa seu patch. Serviços como GitHub Actions, GHCR, S3 e Secrets Manager não possuem uma versão de produto fixada pelo projeto.
