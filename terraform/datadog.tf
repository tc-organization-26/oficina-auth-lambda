variable "datadog_enabled" {
  type        = bool
  default     = false
  description = "Habilita as layers de APM, logs e metricas nas duas Lambdas."
}

variable "datadog_site" {
  type    = string
  default = "datadoghq.com"
}

variable "datadog_version" {
  type    = string
  default = "local"
}

variable "datadog_python_layer_version" {
  type    = number
  default = 127
}

variable "datadog_extension_layer_version" {
  type    = number
  default = 99
}

variable "datadog_api_key_secret_arn" {
  type        = string
  default     = ""
  description = "Secret compartilhado, preenchido pela esteira da API com a DD_API_KEY existente."
  validation {
    condition     = !var.datadog_enabled || can(regex("^arn:aws:secretsmanager:", var.datadog_api_key_secret_arn))
    error_message = "Ao habilitar Datadog, informe o ARN do secret compartilhado da API."
  }
}

locals {
  datadog_layers = var.datadog_enabled ? [
    "arn:aws:lambda:${var.aws_region}:464622532012:layer:Datadog-Python313:${var.datadog_python_layer_version}",
    "arn:aws:lambda:${var.aws_region}:464622532012:layer:Datadog-Extension:${var.datadog_extension_layer_version}"
  ] : []
  datadog_env = var.datadog_enabled ? {
    DD_SITE               = var.datadog_site
    DD_API_KEY_SECRET_ARN = var.datadog_api_key_secret_arn
    DD_TRACE_ENABLED      = "true"
    DD_LOGS_ENABLED       = "true"
    DD_LOGS_INJECTION     = "true"
    DD_ENV                = var.environment
    DD_VERSION            = var.datadog_version
  } : {}
}
