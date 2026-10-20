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
variable "jwt_expiration_seconds" {
  type    = number
  default = 3600
}
