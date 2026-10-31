# AMI de la API. La construye el CI del backend (.github/workflows/deploy.yml)
# y su id se le pasa a infra/backend.yaml como AmiId.
#
# La AMI trae el código, el venv y la unidad systemd. Lo que depende del stack
# (puerto, ARN del secreto de la DB, Cognito) lo escribe el user data del
# launch template en /etc/alquileres/app.env en cada arranque.

packer {
  required_plugins {
    amazon = {
      version = ">= 1.3.0"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "region" { type = string }
variable "project" { type = string }
variable "environment" { type = string }
variable "subnet_id" {
  type        = string
  description = "PublicSubnetA del stack base: la instancia temporal necesita IP pública para que Packer entre por SSH"
}
variable "instance_profile" {
  type        = string
  description = "PackerInstanceProfileName del stack base (permite leer backend/* del bucket de artefactos)"
}
variable "artifacts_bucket" { type = string }
variable "code_version" {
  type        = string
  description = "SHA del commit: prefijo del artefacto en S3 y sufijo del nombre de la AMI"
}

locals {
  timestamp = formatdate("YYYYMMDDhhmmss", timestamp())
}

source "amazon-ebs" "api" {
  region        = var.region
  instance_type = "t3.small"

  source_ami_filter {
    filters = {
      name                = "al2023-ami-2023.*-kernel-6.1-x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    owners      = ["amazon"]
    most_recent = true
  }

  ssh_username                = "ec2-user"
  subnet_id                   = var.subnet_id
  associate_public_ip_address = true
  iam_instance_profile        = var.instance_profile

  # El nombre lleva timestamp porque reintentar el mismo commit no puede
  # chocar con la AMI que dejó el intento anterior.
  ami_name        = "${var.project}-${var.environment}-api-${var.code_version}-${local.timestamp}"
  ami_description = "API de Cuadra (FastAPI/uvicorn) -- commit ${var.code_version}"

  tags = {
    Name        = "${var.project}-${var.environment}-api"
    Project     = var.project
    Environment = var.environment
    CodeVersion = var.code_version
  }
  run_tags = {
    Name = "${var.project}-${var.environment}-packer"
  }
}

build {
  sources = ["source.amazon-ebs.api"]

  provisioner "file" {
    source      = "packer/files/alquileres-api.service"
    destination = "/tmp/alquileres-api.service"
  }

  provisioner "shell" {
    environment_vars = [
      "ARTIFACTS_BUCKET=${var.artifacts_bucket}",
      "CODE_VERSION=${var.code_version}",
    ]
    script = "packer/scripts/provision.sh"
  }
}
