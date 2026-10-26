locals {
  name = "${var.project_name}-${var.environment}"
  tags = { Project = var.project_name, Environment = var.environment, ManagedBy = "Terraform" }
}

data "archive_file" "function" {
  type        = "zip"
  source_dir  = "${path.module}/../package"
  output_path = "${path.module}/function.zip"
}

data "aws_ssm_parameter" "http_api_id" { name = "/${var.project_name}/${var.environment}/edge/http-api-id" }
data "aws_ssm_parameter" "http_api_execution_arn" { name = "/${var.project_name}/${var.environment}/edge/http-api-execution-arn" }
data "aws_ssm_parameter" "app_integration_id" { name = "/${var.project_name}/${var.environment}/edge/app-integration-id" }
data "aws_ssm_parameter" "vpc_id" { name = "/${var.project_name}/${var.environment}/network/vpc-id" }
data "aws_ssm_parameter" "private_subnet_ids" { name = "/${var.project_name}/${var.environment}/network/private-subnet-ids" }
data "aws_ssm_parameter" "database_endpoint" { name = "/${var.project_name}/${var.environment}/database/endpoint" }
data "aws_ssm_parameter" "database_port" { name = "/${var.project_name}/${var.environment}/database/port" }
data "aws_ssm_parameter" "database_name" { name = "/${var.project_name}/${var.environment}/database/name" }
data "aws_ssm_parameter" "database_security_group_id" { name = "/${var.project_name}/${var.environment}/database/security-group-id" }
data "aws_ssm_parameter" "database_master_secret_arn" { name = "/${var.project_name}/${var.environment}/database/master-secret-arn" }

resource "aws_security_group" "login_lambda" {
  name_prefix = "${local.name}-login-lambda-"
  description = "Acesso da Lambda de autenticacao ao PostgreSQL"
  vpc_id      = data.aws_ssm_parameter.vpc_id.value

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "database_from_login_lambda" {
  security_group_id            = data.aws_ssm_parameter.database_security_group_id.value
  referenced_security_group_id = aws_security_group.login_lambda.id
  from_port                    = tonumber(data.aws_ssm_parameter.database_port.value)
  to_port                      = tonumber(data.aws_ssm_parameter.database_port.value)
  ip_protocol                  = "tcp"
  description                  = "Lambda de autenticacao por CPF"
}

resource "aws_secretsmanager_secret" "auth" {
  name                    = "${local.name}/auth"
  recovery_window_in_days = 0
}

resource "aws_lambda_function" "login" {
  function_name    = "${local.name}-login"
  role             = var.lab_role_arn
  runtime          = "python3.13"
  handler          = var.datadog_enabled ? "datadog_lambda.handler.handler" : "handler.login"
  layers           = local.datadog_layers
  memory_size      = 256
  filename         = data.archive_file.function.output_path
  source_code_hash = data.archive_file.function.output_base64sha256
  timeout          = 15

  vpc_config {
    subnet_ids         = jsondecode(data.aws_ssm_parameter.private_subnet_ids.value)
    security_group_ids = [aws_security_group.login_lambda.id]
  }

  environment {
    variables = merge(local.datadog_env, {
      DD_SERVICE                 = "oficina-login"
      DD_LAMBDA_HANDLER          = "handler.login"
      AUTH_SECRET_ID             = aws_secretsmanager_secret.auth.id
      DB_HOST                    = data.aws_ssm_parameter.database_endpoint.value
      DB_PORT                    = data.aws_ssm_parameter.database_port.value
      DB_NAME                    = data.aws_ssm_parameter.database_name.value
      DB_SECRET_ARN              = data.aws_ssm_parameter.database_master_secret_arn.value
      DB_CONNECT_TIMEOUT_SECONDS = tostring(var.database_connect_timeout_seconds)
      JWT_EXPIRATION_SECONDS     = tostring(var.jwt_expiration_seconds)
    })
  }
}

resource "aws_lambda_function" "authorizer" {
  function_name    = "${local.name}-authorizer"
  role             = var.lab_role_arn
  runtime          = "python3.13"
  handler          = var.datadog_enabled ? "datadog_lambda.handler.handler" : "handler.authorizer"
  layers           = local.datadog_layers
  memory_size      = 256
  filename         = data.archive_file.function.output_path
  source_code_hash = data.archive_file.function.output_base64sha256
  timeout          = 10
  environment {
    variables = merge(local.datadog_env, {
      AUTH_SECRET_ID    = aws_secretsmanager_secret.auth.id
      DD_SERVICE        = "oficina-authorizer"
      DD_LAMBDA_HANDLER = "handler.authorizer"
    })
  }
}

resource "aws_apigatewayv2_integration" "login" {
  api_id                 = data.aws_ssm_parameter.http_api_id.value
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.login.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id                            = data.aws_ssm_parameter.http_api_id.value
  name                              = "lambda-jwt-authorizer"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.authorizer.invoke_arn
  identity_sources                  = ["$request.header.Authorization"]
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
}

resource "aws_apigatewayv2_route" "login" {
  api_id    = data.aws_ssm_parameter.http_api_id.value
  route_key = "POST /auth/login"
  target    = "integrations/${aws_apigatewayv2_integration.login.id}"
}

resource "aws_apigatewayv2_route" "app_root" {
  api_id             = data.aws_ssm_parameter.http_api_id.value
  route_key          = "ANY /"
  target             = "integrations/${data.aws_ssm_parameter.app_integration_id.value}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# Public health status only; application returns no dependency details.
resource "aws_apigatewayv2_route" "health" {
  for_each           = toset(["/actuator/health", "/actuator/health/readiness"])
  api_id             = data.aws_ssm_parameter.http_api_id.value
  route_key          = "GET ${each.value}"
  target             = "integrations/${data.aws_ssm_parameter.app_integration_id.value}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "app_proxy" {
  api_id             = data.aws_ssm_parameter.http_api_id.value
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${data.aws_ssm_parameter.app_integration_id.value}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_lambda_permission" "login" {
  statement_id  = "AllowApiGatewayLogin"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.login.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${data.aws_ssm_parameter.http_api_execution_arn.value}/*/*/auth/login"
}

resource "aws_lambda_permission" "authorizer" {
  statement_id  = "AllowApiGatewayAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${data.aws_ssm_parameter.http_api_execution_arn.value}/authorizers/*"
}
