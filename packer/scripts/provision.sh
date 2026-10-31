#!/bin/bash
# Provisioning de la AMI de la API. Lo corre Packer (ver packer/api.pkr.hcl)
# dentro de una instancia temporal de Amazon Linux 2023.
set -euxo pipefail

# Python 3.11: el proyecto pide >=3.11,<3.13 (pyproject.toml) y AL2023 trae
# 3.9 como python3 del sistema.
sudo dnf -y update
sudo dnf -y install python3.11 python3.11-pip tar gzip

sudo useradd --system --create-home --shell /sbin/nologin alquileres || true
sudo mkdir -p /opt/alquileres /etc/alquileres

# El artefacto lo subió el CI antes de llamar a Packer. La instancia lo lee
# con el instance profile PackerInstanceProfile del stack base.
aws s3 cp "s3://${ARTIFACTS_BUCKET}/backend/${CODE_VERSION}/app.tgz" /tmp/app.tgz
sudo mkdir -p /opt/alquileres/app
sudo tar -xzf /tmp/app.tgz -C /opt/alquileres/app

sudo python3.11 -m venv /opt/alquileres/venv
sudo /opt/alquileres/venv/bin/pip install --no-cache-dir --upgrade pip
sudo /opt/alquileres/venv/bin/pip install --no-cache-dir \
  -r /opt/alquileres/app/requirements.txt

# Los PDF de informes y las fotos subidas se escriben en runtime.
sudo mkdir -p /opt/alquileres/app/app/static/reports /opt/alquileres/app/app/static/uploads
sudo chown -R alquileres:alquileres /opt/alquileres

sudo mv /tmp/alquileres-api.service /etc/systemd/system/alquileres-api.service
sudo chown root:root /etc/systemd/system/alquileres-api.service
sudo systemctl daemon-reload
# Habilitado pero no arrancado: arranca en el primer boot real, cuando el
# user data ya dejó /etc/alquileres/app.env.
sudo systemctl enable alquileres-api
