# Oficina - Lambda de Autenticacao

Implementa login serverless, emissao de JWT compatível com a aplicação Spring e Lambda Authorizer do API Gateway.

## Testes

```bash
python -m unittest discover -s tests
```

O deploy usa Terraform e depende do API Gateway criado por `oficina-k8s-infra`. Configure `AWS_ROLE_ARN`, `AWS_REGION`, `TF_STATE_BUCKET`, `AUTH_LOGIN`, `AUTH_PASSWORD`, `JWT_SECRET` e `ADMIN_ID` no GitHub.

```text
POST /auth/login -> Lambda -> JWT -> Lambda Authorizer -> API no EKS
```
