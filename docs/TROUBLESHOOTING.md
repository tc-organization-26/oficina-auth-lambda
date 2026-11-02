# Troubleshooting — oficina-auth-lambda

[README](../README.md) · [Validação local e execução manual](VALIDACAO-E-EXECUCAO-MANUAL.md) · [Execução no laboratório AWS](EXECUCAO-LAB-AWS.md)

## Troubleshooting de outros repositórios da solução

- [Aplicação: Docker, Java, API, Pods e Datadog](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/main/docs/TROUBLESHOOTING.md).
- [Plataforma: bootstrap, EKS, rede e entrada HTTP](https://github.com/tc-organization-26/oficina-k8s-infra/blob/main/docs/TROUBLESHOOTING.md).
- [Banco: RDS, conectividade, credenciais e snapshots](https://github.com/tc-organization-26/oficina-db-infra/blob/main/docs/TROUBLESHOOTING.md).


Este guia parte do sintoma, indica o que conferir e orienta a correção. Execute os comandos na raiz deste repositório, salvo indicação diferente. Cada bloco é um procedimento de diagnóstico independente; os exemplos usam PowerShell.

Nos exemplos AWS, use uma sessão válida e defina:

```powershell
$oficinaEnv = "hom"
$oficinaRegion = "us-east-1"
$env:AWS_DEFAULT_REGION = $oficinaRegion
aws sts get-caller-identity
```

Para produção, altere o ambiente para `prod` e confira a conta antes de prosseguir. As credenciais do GitHub não configuram o terminal; o [guia AWS](EXECUCAO-LAB-AWS.md#credenciais-e-ferramentas) explica os pré-requisitos de acesso. Ao compartilhar evidências, informe ambiente, horário, URL/caminho, status HTTP, ID do workflow e mensagem de erro. Remova tokens, senhas e valores de secrets dos trechos compartilhados.

## Assuntos

- [Python, testes e empacotamento](#python-testes-e-empacotamento)
- [Credenciais AWS e GitHub Actions](#credenciais-aws-e-github-actions)
- [Terraform e state S3](#terraform-e-state-s3)
- [Dependências, funções e secrets](#dependências-funções-e-secrets)
- [Login por CPF e respostas HTTP](#login-por-cpf-e-respostas-http)
- [Authorizer, JWT e rotas do Gateway](#authorizer-jwt-e-rotas-do-gateway)
- [Rede privada e observabilidade](#rede-privada-e-observabilidade)
- [Executando destroy da autenticação](#executando-destroy-da-autenticação)

## Python, testes e empacotamento

### Python não encontrado ou testes falham ao importar handler

Use Python 3.13 e execute na raiz: `python -m unittest discover -s tests`. Confira `python --version` e qual intérprete o terminal utiliza. Os testes ajustam o caminho `src` e usam mocks; não precisam de banco ou AWS reais. Chamadas manuais ao handler fora desse contexto podem tentar acessar dependências reais.

### ModuleNotFoundError para pg8000, scramp ou observability

Monte o pacote conforme o [guia de validação e execução manual](VALIDACAO-E-EXECUCAO-MANUAL.md#empacotamento), copiando todos os `src/*.py`, não apenas o handler. `pg8000`/`scramp` vêm de `requirements.txt`; `observability.py` é módulo do próprio repositório. A Lambda fornece boto3 no runtime, mas uma invocação local que use Secrets Manager precisa do SDK no intérprete local.

### ImportError envolvendo make_channel_binding

O projeto fixa `pg8000==1.31.2` e `scramp==1.4.18` por compatibilidade. Não atualize somente scramp. Confira o pacote que será enviado, não apenas a instalação global:

```powershell
python -c "import sys; sys.path.insert(0, 'package'); import pg8000.dbapi, scramp; assert callable(scramp.make_channel_binding)"
```

Se houve troca de versões, reconstrua um diretório `package` limpo e remonte antes do plano. Uma pasta antiga pode misturar arquivos de dependências diferentes.

### archive_file falha, ZIP vazio ou mudança Python não chega à Lambda

O Terraform fica em `terraform/` e empacota `../package`. Crie o pacote antes do validate/plan/apply. O arquivo `terraform/function.zip` é gerado; não edite o ZIP manualmente como fonte. O hash do pacote determina a atualização; após alterar `src`, copie novamente os módulos e gere novo plano. Confira branch/SHA publicado no workflow.

## Credenciais AWS e GitHub Actions

### ExpiredToken, InvalidClientTokenId ou assinatura inválida

Renove juntos `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e `AWS_SESSION_TOKEN` na organização (com acesso ao repositório) ou nos Repository secrets. Atualize também o terminal utilizado. Verifique espaços acidentais e relógio da máquina se houver erro de assinatura/tempo. Repita `aws sts get-caller-identity`; ele precisa identificar a conta esperada antes de um novo deploy.

Se o erro persistir no Actions, confira se um Repository secret está sobrescrevendo o valor renovado da organização ou se há um secret de Environment sobrescrevendo a configuração compartilhada. Reinicie a execução após corrigir; não é necessário refazer o bootstrap só para renovar credenciais.

### ParameterNotFound, ResourceNotFound ou recursos do ambiente errado

Confirme `AWS_REGION`, o ambiente (`hom`/`prod`), o prefixo `/oficina/ENV` e a conclusão da etapa anterior. Plataforma, banco e autenticação usam `dev` como padrão Terraform; a observabilidade da API usa `hom`. Selecione explicitamente `hom` ou `prod` para integrar o ambiente implantado. A primeira instalação segue bootstrap → plataforma → banco → autenticação → API → reexecução da autenticação para Datadog.

```powershell
aws ssm get-parameters-by-path --path "/oficina/$oficinaEnv" --recursive --query "Parameters[].Name" --output table
```

Uma lista vazia pode indicar conta/região errada ou pré-requisito ainda ausente. `AccessDenied` significa falta de permissão, não prova que o recurso não existe.

### Deploy pulado, execução aguardando aprovação ou PR sem checks novos

`fase-3` valida; apenas `homologacao` e `main` fazem deploy. O merge para `homologacao` já dispara a implantação em `hom`; não execute outro deploy manual após um merge bem-sucedido. Abrir um PR não dispara uma execução adicional: os workflows atuais não têm gatilho `pull_request`.

Se o job aguardar aprovação, confira as regras do GitHub Environment `homologacao`/`producao`. Se aguardar outro workflow, confira a concorrência configurada. Os runners são `ubuntu-latest`; instruções antigas para instalar um runner Windows self-hosted não se aplicam.

### Workflow não aparece, ferramentas faltam ou execução usa código antigo

Confira se o arquivo está em `.github/workflows`, se a branch selecionada contém a versão esperada e se o workflow permite execução manual. Uma alteração local ainda não enviada ao GitHub não muda o Actions. Na interface, procure o nome do workflow; no CLI, use o nome do arquivo mostrado no README.

`command not found` em um runner indica que a etapa de setup não foi executada ou que foi usada outra branch/versão do workflow. Confira o log dessa etapa antes de instalar ferramentas por fora da esteira. Para uma execução pendente, confira disponibilidade do runner e limites de uso da organização.

### PR automático falha com Resource not accessible by integration ou 403

Confira permissões de escrita e criação de PRs em **Settings → Actions → General → Workflow permissions**, além das políticas da organização. A promoção usa `GITHUB_TOKEN`; `GH_ADMIN_TOKEN` é reservado ao bootstrap. Verifique se a execução de origem passou e se há commits a promover. PR já existente é reutilizado; falha de deploy impede a promoção seguinte.

### IAM nega CreateRole, CreateOpenIDConnectProvider, PassRole ou leitura de secrets

O fluxo educacional atual reutiliza LabRole e não cria roles/OIDC. Tentativas de criação podem indicar código de outra branch ou bootstrap legado. Leia a ação e o recurso negados no log e confira a role configurada; reutilizar LabRole não garante todas as permissões necessárias. A instituição precisa liberar a ação quando houver negação imposta pela conta. Não troque para credenciais de outra conta mantendo o mesmo state.

## Terraform e state S3

### Terraform ausente, pasta errada ou sintaxe inválida

Use Terraform compatível com o projeto (o CI fixa `1.15.9`, mínimo `1.10.0`). Confira `terraform version`. Os comandos abaixo usam a pasta `terraform` a partir da raiz. Em `terraform.tfvars`, use HCL com valores literais ou variáveis `TF_VAR_*`; expressões Spring como `${VAR:padrao}` não são válidas nesse arquivo. `TF_VAR_*` não substitui os argumentos do backend.

```powershell
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
```

`fmt -check` informa divergência de formato; aplique `fmt` nos arquivos que alterou e revise o diff. O `init -backend=false` valida sem acessar o state S3, mas ainda pode baixar providers/módulos. Ele não prepara a aplicação na AWS.

### Falha no download, checksum ou provider incompatível

Confira rede, proxy, certificados e as versões de Terraform/providers declaradas. Use o lockfile versionado; um erro de checksum pode indicar pacote corrompido, plataforma sem hash registrado ou mudança de dependências. Não apague o lockfile nem rode `init -upgrade` como correção automática: isso pode selecionar versões diferentes. Mudanças de provider devem ser intencionais, revisadas e validadas antes do plano.

### Bucket ausente, AccessDenied ou Backend configuration changed

Conclua o bootstrap e confirme o bucket em `TF_STATE_BUCKET`, conta e região. Uma resposta 403 de `head-bucket` não prova ausência do bucket. O backend precisa de acesso aos objetos do state e do lock. No terminal, informe o mesmo bucket e a mesma chave do CI/CD:

```powershell
$oficinaBucket = "BUCKET_DISTRIBUIDO_PELO_BOOTSTRAP"
$env:TF_VAR_environment = $oficinaEnv
$env:TF_VAR_aws_region = $oficinaRegion
$env:TF_VAR_lab_role_arn = "arn:aws:iam::ACCOUNT_ID:role/LabRole"
aws s3api head-bucket --bucket $oficinaBucket
terraform -chdir=terraform init -reconfigure `
  -backend-config="bucket=$oficinaBucket" `
  -backend-config="key=oficina/auth/$oficinaEnv.tfstate" `
  -backend-config="region=$oficinaRegion" `
  -backend-config="encrypt=true" `
  -backend-config="use_lockfile=true"
```

`-reconfigure` seleciona a configuração; não transfere automaticamente os recursos de outro state. Se há uma migração real de backend, preserve backup e planeje a migração, em vez de apontar um state vazio para recursos existentes. Pedidos de `secret_suffix`, `KUBE_CONFIG_BASE64` ou backend Kubernetes indicam instruções antigas da fase 2.

### Error acquiring the state lock

Confira execuções ativas no Actions e terminais. Aguarde a operação que possui o lock; interromper o acompanhamento não significa que o processo parou. As esteiras serializam sua própria branch, mas um apply manual ainda pode concorrer.

Somente após confirmar que não há operação ativa e que o backend acima é o correto, remova um lock abandonado com o ID exibido no erro:

```powershell
terraform -chdir=terraform force-unlock ID_EXATO_MOSTRADO_NO_ERRO
```

Não use `-lock=false`, não reutilize um ID de exemplo e não apague o objeto `.tflock` como rotina. Consulte a [referência do force-unlock](https://developer.hashicorp.com/terraform/cli/commands/force-unlock).

### Apply interrompido, recurso já existente ou plano propõe recriação inesperada

Uma execução com falha pode ter criado parte dos recursos. Preserve state e logs, corrija a causa e gere um novo plano no mesmo backend; não reaplique um plano salvo antes de mudanças no ambiente. Se o plano tentar criar tudo novamente, confira a chave, workspace e conta. O projeto usa o workspace padrão e chaves distintas por ambiente.

Recursos existentes fora do state exigem avaliação de importação, não exclusão por tentativa. Revise substituições e destruições antes de aplicar. Não edite o state manualmente para esconder uma divergência.

## Dependências, funções e secrets

### SSM ausente ou apply falha antes de criar as rotas

Implante plataforma e RDS no mesmo ambiente. São consumidos IDs do Gateway/integração/VPC/sub-redes e dados do banco. A [referência técnica](../README.md#configuração-terraform-e-descoberta) lista os caminhos. `hom` e `prod` possuem IDs e secrets distintos; não misture inputs entre eles.

### InvalidParameterValueException, PassRole ou falha ao criar interfaces de rede

As duas funções usam `lab_role_arn`; a role precisa poder ser assumida pelo serviço Lambda. O login é ligado à VPC e precisa das permissões de ENI, logs e leitura dos secrets utilizados. Confira a ação/role negada, sub-redes da mesma VPC, SG válido e limitações da conta. Um ARN sintaticamente válido não garante trust policy/permissões corretas.

### Função Pending, Failed, LastUpdateStatus Failed ou handler incorreto

```powershell
aws lambda get-function-configuration --function-name "oficina-$oficinaEnv-login" --query "{State:State,Reason:StateReason,Update:LastUpdateStatus,UpdateReason:LastUpdateStatusReason,Runtime:Runtime,Handler:Handler,Layers:Layers[].Arn}" --output json
aws lambda get-function-configuration --function-name "oficina-$oficinaEnv-authorizer" --query "{State:State,Reason:StateReason,Update:LastUpdateStatus,Handler:Handler}" --output json
```

Espere a atualização terminar. Sem Datadog, os handlers são `handler.login` e `handler.authorizer`. Com instrumentação, o wrapper muda e `DD_LAMBDA_HANDLER` aponta ao handler original. Confira runtime Python 3.13, arquitetura x86_64, pacote e layers compatíveis. Uma atualização de configuração pode ter falhado mesmo com a função anterior ainda ativa.

### Secret JWT ausente, sem versão ou com chave JSON errada

O Terraform cria `oficina-ENV/auth`; o workflow grava o JSON com a chave `jwtSecret` depois do apply. Um apply manual sozinho deixa esse conteúdo por configurar. Confira metadata/versões sem imprimir o valor:

```powershell
aws secretsmanager describe-secret --secret-id "oficina-$oficinaEnv/auth" --query "{Name:Name,Versions:VersionIdsToStages,LastChanged:LastChangedDate}" --output json
```

Configure `JWT_SECRET` nos Actions secrets do repositório `oficina-auth-lambda` e reexecute a etapa de deploy. Não forneça `AUTH_LOGIN`, `AUTH_PASSWORD` ou `ADMIN_ID`: o login atual consulta cliente por CPF. Uma chave vazia/curta pode causar incompatibilidade com a validação HS256 do Java mesmo se o Python conseguir assinar o token.

### Secret mudou, mas funções/API continuam com valor anterior

Os secrets de autenticação e banco são mantidos em cache por instância de execução Lambda. A API recebe uma cópia da chave/credencial durante seu deploy. Depois de corrigir ou rotacionar secrets, coordene a atualização dos consumidores; instâncias Lambda aquecidas podem manter cache. Gere um token novo com a configuração alinhada. Não copie valores reais para logs para comparar chaves.

## Login por CPF e respostas HTTP

### Teste de login com URL antiga ou corpo de autenticação Java

Use a URL do Gateway publicado no resumo do deploy, sem stage adicional. O endpoint é `POST /auth/login` e recebe JSON `{ "cpf": "003.619.370-40" }`. `login`/`senha` pertencem ao login Java local e ao port-forward. Importe a [collection completa do Insomnia](https://github.com/tc-organization-26/gestao-oficina-tc-1/blob/main/src/main/resources/insomnia/collection.yaml), ajuste `BASE_URL` e copie o token de sucesso para `TOKEN` antes da consulta protegida.

### Login retorna 400

Confira JSON, corpo objeto, campo `cpf` como string e CPF com dígitos verificadores válidos. Formatos aceitos são 11 dígitos ou pontuação completa. CPF numérico pode perder zeros iniciais. O handler retorna 400 para corpo/CPF inválido e também captura erros de campos/configuração que levantem KeyError/ValueError; se o corpo estiver correto, confira secret/variáveis e logs de integração antes de atribuir o erro somente ao cliente.

### Login retorna 404 ou 403

404 indica que a consulta não encontrou o cliente; 403 indica cliente inativo. Aguarde a API aplicar Flyway e confirme o banco/ambiente usado. O CPF é normalizado para dígitos e consultado em `cliente.cpf_cnpj`. O cliente fictício vem da migration V3; este Terraform não cria tabelas nem executa seed. Os códigos se referem à resposta do login, não a todas as rotas Java.

### Login retorna 500 ou demora até timeout

Correlacione horário/request ID com CloudWatch:

```powershell
aws logs tail "/aws/lambda/oficina-$oficinaEnv-login" --since 15m --format short
```

Confira secret RDS, TLS, SG, endpoint, porta/database, permissões e saída para Secrets Manager. O timeout de conexão ao banco é 5 segundos por padrão e o timeout da função login é 15 segundos. Aumentar o timeout não corrige rota/SG ausente. `relation cliente does not exist` pede concluir Flyway; `password authentication failed` pede revisar a credencial/cache; erro TLS pede revisar certificados/cliente.

## Authorizer, JWT e rotas do Gateway

### Login funciona, mas rota protegida retorna 401 ou 403

Confira `Authorization: Bearer TOKEN`, maiúsculas do prefixo, token sem aspas, expiração, chave e ambiente. A identidade do Gateway procura `$request.header.Authorization`; token ausente pode ser recusado antes de invocar a Lambda. O Authorizer valida assinatura/expiração e precisa dos claims usados no contexto. Depois dele, o Spring valida o JWT novamente, inclusive compatibilidade de `sub`/`papel` com o Java. Um token feito manualmente pode passar por uma etapa e falhar na outra.

### Gateway responde 500 ou Authorizer configuration error

```powershell
aws logs tail "/aws/lambda/oficina-$oficinaEnv-authorizer" --since 15m --format short
```

Confira permissão de invocação pelo Gateway, ARN da função, authorizer payload 2.0, resposta `isAuthorized` e leitura do secret. Erros de permissão/rede/secret não são necessariamente convertidos em token recusado pelo handler; veja a exceção. Se não há log, confira permissão de escrita de logs e se a rota realmente chegou à função.

### Readiness/Swagger retorna 404, 403 ou integração inválida

Este repositório cria as rotas públicas POST login e GET health/readiness, além de `ANY /` e `ANY /{proxy+}` com autorização CUSTOM. Swagger e outros caminhos genéricos exigem JWT. Confira IDs e vínculos:

```powershell
$oficinaApiId = aws ssm get-parameter --name "/oficina/$oficinaEnv/edge/http-api-id" --query Parameter.Value --output text
aws apigatewayv2 get-routes --api-id $oficinaApiId --query "Items[].{Route:RouteKey,Auth:AuthorizationType,Target:Target,Authorizer:AuthorizerId}" --output table
```

Uma verificação por HEAD não usa as rotas GET públicas e pode ser recusada. Rota correta com 502/503/504 pede conferir VPC Link/NLB/API no guia da plataforma. O Authorizer retorna uma decisão; ele não faz o proxy HTTP para a API.

## Rede privada e observabilidade

### Login não alcança Secrets Manager ou RDS

A Lambda de login usa sub-redes privadas e precisa de saída para serviços AWS; o projeto habilita NAT na plataforma. Colocá-la em uma sub-rede pública não lhe fornece automaticamente IP público. Confira rotas/NAT, DNS, SG da Lambda e regra de entrada no SG RDS. O Authorizer fica fora da VPC e pode funcionar enquanto só o login falha. Consulte o [diagnóstico oficial de rede Lambda](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting-networking.html).

### Logs não aparecem ou Datadog está desabilitado

Confira a função/ambiente e a permissão de logs da LabRole. O workflow só habilita layers se encontrar `oficina-ENV/datadog`, criado pela API. A ausência do secret gera aviso e deploy sem tracer; AccessDenied ao consultá-lo é falha. Após o primeiro deploy da API, reexecute a autenticação. Não duplique as chaves Datadog no GitHub deste repositório.

### Layer não é encontrada, extensão falha ou trace Java não é o mesmo da Lambda

Confira região, arquitetura, Python 3.13, versões das layers e permissão de acesso. O site Datadog deve ser o mesmo da API; o login precisa de saída HTTPS. Use `service:oficina-login` ou `service:oficina-authorizer` e o ambiente correto. O Authorizer e o Java podem produzir traces separados; a autorização do Gateway não representa uma chamada HTTP instrumentada direta entre os dois.

## Executando destroy da autenticação

### Destroy falha ou secret JWT foi apagado

Remova consumidores da API antes da autenticação e destrua este componente antes do banco/Gateway. A regra no SG RDS pertence a este state, embora o banco pertença a outro repositório. O secret auth usa janela de recuperação zero: sua exclusão não tem período de restauração. Para uma recriação intencional, publique o secret novamente e atualize a API para a mesma chave; tokens antigos deixam de funcionar quando a chave muda. Siga o [procedimento de destroy](EXECUCAO-LAB-AWS.md#executando-destroy).