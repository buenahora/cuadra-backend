"""De dónde sale la región para los clientes de boto3.

Existe por un bug que costó un deploy entero: la instancia tenía
`AWS_REGION=us-east-1` puesta y la app igual moría al arrancar con
`botocore.exceptions.NoRegionError: You must specify a region`. El motivo es
que **botocore resuelve la región de `AWS_DEFAULT_REGION`, no de
`AWS_REGION`**, así que dejarle la resolución a botocore con solo la segunda
puesta no alcanza. La app la pasa explícita.
"""

from __future__ import annotations

from app.core import secrets
from app.core.config import settings


def test_la_config_gana(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", "sa-east-1")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    assert secrets._region() == "sa-east-1"


def test_cae_a_aws_region(monkeypatch):
    """El nombre que botocore NO mira por su cuenta: por eso lo mira la app."""
    monkeypatch.setattr(settings, "aws_region", "")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert secrets._region() == "us-east-1"


def test_cae_a_aws_default_region(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", "")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    assert secrets._region() == "us-east-2"


def test_sin_nada_devuelve_none(monkeypatch):
    """En una máquina de desarrollo botocore resuelve del config file o el
    perfil, así que no hay que forzarle una región inventada."""
    monkeypatch.setattr(settings, "aws_region", "")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert secrets._region() is None
