terraform {
  required_version = ">= 1.10.0"
  backend "s3" {}
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags { tags = local.tags }
}

