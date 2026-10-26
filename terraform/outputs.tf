output "login_function_name" { value = aws_lambda_function.login.function_name }
output "authorizer_function_name" { value = aws_lambda_function.authorizer.function_name }
output "auth_secret_arn" { value = aws_secretsmanager_secret.auth.arn }
output "login_lambda_security_group_id" { value = aws_security_group.login_lambda.id }
