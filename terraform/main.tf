locals {
  name = "${var.project_name}-${var.environment}"
  tags = { Project = var.project_name, Environment = var.environment, ManagedBy = "Terraform" }
}

data "archive_file" "function" {
  type        = "zip"
  source_file = "${path.module}/../src/handler.py"
  output_path = "${path.module}/function.zip"
}

data "aws_ssm_parameter" "http_api_id" { name = "/${var.project_name}/${var.environment}/edge/http-api-id" }
data "aws_ssm_parameter" "http_api_execution_arn" { name = "/${var.project_name}/${var.environment}/edge/http-api-execution-arn" }
data "aws_ssm_parameter" "app_integration_id" { name = "/${var.project_name}/${var.environment}/edge/app-integration-id" }

resource "aws_secretsmanager_secret" "auth" {
  name                    = "${local.name}/auth"
  recovery_window_in_days = 0
}

resource "aws_lambda_function" "login" {
  function_name    = "${local.name}-login"
  role             = var.lab_role_arn
  runtime          = "python3.13"
  handler          = "handler.login"
  filename         = data.archive_file.function.output_path
  source_code_hash = data.archive_file.function.output_base64sha256
  timeout          = 10
  environment { variables = { AUTH_SECRET_ID = aws_secretsmanager_secret.auth.id, JWT_EXPIRATION_SECONDS = tostring(var.jwt_expiration_seconds) } }
}

resource "aws_lambda_function" "authorizer" {
  function_name    = "${local.name}-authorizer"
  role             = var.lab_role_arn
  runtime          = "python3.13"
  handler          = "handler.authorizer"
  filename         = data.archive_file.function.output_path
  source_code_hash = data.archive_file.function.output_base64sha256
  timeout          = 10
  environment { variables = { AUTH_SECRET_ID = aws_secretsmanager_secret.auth.id } }
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
