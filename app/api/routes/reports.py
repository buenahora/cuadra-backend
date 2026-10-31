import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_current_user,
    get_listings_repo,
    get_market_snapshots_repo,
    get_reports_repo,
    get_zones_repo,
)
from app.core.config import settings
from app.repositories.base import ListingsRepository, ReportsRepository, ZonesRepository
from app.repositories.memory.repo import MarketSnapshotsRepositoryMemory
from app.repositories.models import ReportRow, UserRow
from app.schemas.report import ReportCreate, ReportOut
from app.services import market as market_service
from app.services.report_pdf import generate_report_pdf

router = APIRouter(tags=["reports"])


def _to_out(row: ReportRow) -> ReportOut:
    return ReportOut(
        id=row.id,
        generado_por=row.generado_por,
        titulo=row.titulo,
        destinatario_nombre=row.destinatario_nombre,
        zone_id=row.zone_id,
        dormitorios_bucket=row.dormitorios_bucket,
        periodo=row.periodo,
        secciones_incluidas=row.secciones_incluidas,
        pdf_url=row.pdf_url,
        generado_en=row.generado_en,
    )


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    current_user: UserRow = Depends(get_current_user),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    snapshots_repo: MarketSnapshotsRepositoryMemory = Depends(get_market_snapshots_repo),
    reports_repo: ReportsRepository = Depends(get_reports_repo),
) -> ReportOut:
    """Informe PDF de valuación (S3C) -- combina MarketStat +
    MarketSnapshot + comparables para la zona/tipología elegida."""
    zone = zones_repo.get(payload.zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Zona '{payload.zone_id}' no existe")

    bucket = payload.dormitorios_bucket.value
    all_stats = market_service.compute_stats(listings_repo.list_active(), payload.zone_id, bucket)
    stats = all_stats[0] if all_stats else None

    history_rows = snapshots_repo.list_seed_history(payload.zone_id, bucket)
    history = [(r.periodo, r.precio_mediana) for r in history_rows]
    if stats and stats.muestra_confiable:
        history.append((date.today().replace(day=1), stats.precio_mediana))

    comparables = [
        l for l in listings_repo.list_active()
        if l.zone_id == payload.zone_id and l.dormitorios_bucket == bucket
    ]

    report_id = uuid.uuid4()
    generate_report_pdf(
        report_id=report_id,
        titulo=payload.titulo,
        destinatario_nombre=payload.destinatario_nombre,
        barrio=zone.nombre,
        dormitorios_bucket=bucket,
        periodo=payload.periodo,
        secciones=payload.secciones_incluidas,
        stats=stats,
        history=history,
        comparables=comparables,
        output_dir=Path(settings.reports_dir),
    )

    row = ReportRow(
        id=report_id,
        generado_por=current_user.id,
        titulo=payload.titulo,
        destinatario_nombre=payload.destinatario_nombre,
        zone_id=payload.zone_id,
        dormitorios_bucket=bucket,
        periodo=payload.periodo.value,
        secciones_incluidas=[s.value for s in payload.secciones_incluidas],
        pdf_url=f"/static/reports/{report_id}.pdf",
        generado_en=datetime.now(timezone.utc),
    )
    reports_repo.create(row)
    return _to_out(row)


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(
    report_id: uuid.UUID,
    current_user: UserRow = Depends(get_current_user),
    reports_repo: ReportsRepository = Depends(get_reports_repo),
) -> ReportOut:
    report = reports_repo.get(report_id)
    if report is None or report.generado_por != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Informe no encontrado")
    return _to_out(report)


@router.get("/users/me/reports", response_model=list[ReportOut])
def my_reports(
    current_user: UserRow = Depends(get_current_user),
    reports_repo: ReportsRepository = Depends(get_reports_repo),
) -> list[ReportOut]:
    return [_to_out(r) for r in reports_repo.list_by_user(current_user.id)]
