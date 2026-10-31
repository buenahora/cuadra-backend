"""Genera el PDF de valuación del corredor (S3C,
cuadra-data/docs/data-model.md §9) a partir de MarketStat/MarketSnapshot y
comparables reales -- no es un mock, el archivo se escribe a disco y se
sirve como estático. Cuando la data layer real reemplace al store en
memoria, la única diferencia es de dónde vienen `stats`/`history`/
`comparables`; la forma del documento no cambia.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.repositories.models import ListingRow
from app.schemas.common import PeriodoReporte, SeccionReporte
from app.services.market import ZoneDormsStats

_MESES_POR_PERIODO = {
    PeriodoReporte.tres_meses: 3,
    PeriodoReporte.seis_meses: 6,
    PeriodoReporte.doce_meses: 12,
}


class _ReportPdf(FPDF):
    def line(self, text: str, *, size: int = 11, bold: bool = False, italic: bool = False, height: float = 7) -> None:
        style = ("B" if bold else "") + ("I" if italic else "")
        self.set_font("Helvetica", style, size)
        # new_x/new_y explícitos: el default de fpdf2 (XPos.RIGHT) deja el
        # cursor pegado al margen derecho después de un multi_cell(w=0,...),
        # lo que revienta la siguiente llamada con "Not enough horizontal
        # space to render a single character".
        self.multi_cell(0, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generate_report_pdf(
    *,
    report_id: UUID,
    titulo: str,
    destinatario_nombre: str,
    barrio: str,
    dormitorios_bucket: str,
    periodo: PeriodoReporte,
    secciones: list[SeccionReporte],
    stats: ZoneDormsStats | None,
    history: list[tuple[date, float]],
    comparables: list[ListingRow],
    output_dir: Path,
) -> Path:
    pdf = _ReportPdf()
    pdf.add_page()

    pdf.line(titulo, size=18, bold=True, height=10)
    pdf.line(f"Preparado para: {destinatario_nombre}")
    pdf.line(f"Zona: {barrio}  |  Dormitorios: {dormitorios_bucket}  |  Generado: {date.today().isoformat()}")
    pdf.ln(4)

    if stats is None or not stats.muestra_confiable:
        pdf.line(
            "No hay muestra suficiente de avisos activos para esta zona y tipología. "
            "Este informe no incluye estadística de mercado.",
            italic=True,
        )
    else:
        if SeccionReporte.precio_mediano in secciones:
            pdf.line("Precio mediano", size=13, bold=True, height=8)
            pdf.line(f"$ {stats.precio_mediana:,.0f} / mes  (basado en {stats.avisos_activos} avisos activos)")
            pdf.ln(2)

        if SeccionReporte.rango_de_precios in secciones:
            pdf.line("Rango de precios", size=13, bold=True, height=8)
            pdf.line(f"Mínimo: $ {stats.precio_min:,.0f}   Máximo: $ {stats.precio_max:,.0f}")
            pdf.ln(2)

        if SeccionReporte.evolucion_historica in secciones:
            pdf.line("Evolución histórica", size=13, bold=True, height=8)
            n_meses = _MESES_POR_PERIODO[periodo]
            for periodo_mes, mediana in history[-n_meses:]:
                pdf.line(f"{periodo_mes.strftime('%Y-%m')}: $ {mediana:,.0f}", size=10, height=6)
            pdf.ln(2)

    if SeccionReporte.avisos_comparables in secciones:
        pdf.line("Avisos comparables", size=13, bold=True, height=8)
        if not comparables:
            pdf.line("Sin avisos comparables activos en esta combinación.", size=10, height=6)
        for listing in comparables[:15]:
            pdf.line(
                f"- {listing.direccion} -- $ {listing.precio:,.0f} -- {listing.metraje_m2} m2",
                size=10, height=6,
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report_id}.pdf"
    pdf.output(str(path))
    return path
