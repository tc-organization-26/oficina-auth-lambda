variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "project_name" {
  type    = string
  default = "oficina"
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "lab_role_arn" {
  description = "ARN da LabRole preexistente usada pelas funcoes Lambda no ambiente educacional."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+", var.lab_role_arn))
    error_message = "lab_role_arn deve ser o ARN de uma role IAM valida."
  }
}
variable "jwt_expiration_seconds" {
  type    = number
  default = 3600
}
