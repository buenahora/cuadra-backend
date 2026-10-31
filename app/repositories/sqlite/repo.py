"""Implementaciones SQLite de UsersRepository/FavoritesRepository/
InquiriesRepository/ReportsRepository (app/repositories/base.py) -- mismo
contrato que las versiones en memoria que reemplazan
(app/repositories/memory/repo.py), así que app/api/deps.py es el único
lugar que cambia al enchufarlas."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from app.repositories.models import FavoriteRow, InquiryRow, ReportRow, UserRow
from app.repositories.sqlite.connection import get_connection


def _row_to_user(row: sqlite3.Row) -> UserRow:
    return UserRow(
        id=UUID(row["id"]),
        nombre_completo=row["nombre_completo"],
        email=row["email"],
        telefono=row["telefono"],
        password_hash=row["password_hash"],
        es_corredor=bool(row["es_corredor"]),
        google_id=row["google_id"],
        creado_en=datetime.fromisoformat(row["creado_en"]),
    )


class UsersRepositorySQLite:
    def create(
        self,
        nombre_completo: str,
        email: str,
        telefono: str | None,
        password_hash: str,
        es_corredor: bool = False,
    ) -> UserRow:
        user = UserRow(
            id=uuid4(),
            nombre_completo=nombre_completo,
            email=email.lower(),
            telefono=telefono,
            password_hash=password_hash,
            es_corredor=es_corredor,
            google_id=None,
            creado_en=datetime.now(timezone.utc),
        )
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users"
                " (id, nombre_completo, email, telefono, password_hash, es_corredor, google_id, creado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(user.id), user.nombre_completo, user.email, user.telefono,
                    user.password_hash, int(user.es_corredor), user.google_id,
                    user.creado_en.isoformat(),
                ),
            )
        return user

    def get_by_id(self, user_id: UUID) -> UserRow | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        return _row_to_user(row) if row else None

    def get_by_email(self, email: str) -> UserRow | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        return _row_to_user(row) if row else None


def _row_to_favorite(row: sqlite3.Row) -> FavoriteRow:
    return FavoriteRow(
        user_id=UUID(row["user_id"]),
        listing_id=UUID(row["listing_id"]),
        creado_en=datetime.fromisoformat(row["creado_en"]),
    )


class FavoritesRepositorySQLite:
    def add(self, user_id: UUID, listing_id: UUID) -> FavoriteRow:
        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO favorites (user_id, listing_id, creado_en) VALUES (?, ?, ?)",
                (str(user_id), str(listing_id), now.isoformat()),
            )
            row = conn.execute(
                "SELECT * FROM favorites WHERE user_id = ? AND listing_id = ?",
                (str(user_id), str(listing_id)),
            ).fetchone()
        return _row_to_favorite(row)

    def remove(self, user_id: UUID, listing_id: UUID) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND listing_id = ?",
                (str(user_id), str(listing_id)),
            )
        return cur.rowcount > 0

    def list_by_user(self, user_id: UUID) -> list[FavoriteRow]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM favorites WHERE user_id = ?", (str(user_id),)
            ).fetchall()
        return [_row_to_favorite(r) for r in rows]

    def is_favorite(self, user_id: UUID, listing_id: UUID) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND listing_id = ?",
                (str(user_id), str(listing_id)),
            ).fetchone()
        return row is not None


def _row_to_inquiry(row: sqlite3.Row) -> InquiryRow:
    return InquiryRow(
        id=UUID(row["id"]),
        listing_id=UUID(row["listing_id"]),
        remitente_user_id=UUID(row["remitente_user_id"]),
        nombre=row["nombre"],
        email=row["email"],
        telefono=row["telefono"],
        fecha_mudanza=date.fromisoformat(row["fecha_mudanza"]) if row["fecha_mudanza"] else None,
        mensaje=row["mensaje"],
        respuesta=row["respuesta"],
        creado_en=datetime.fromisoformat(row["creado_en"]),
        respondido_en=datetime.fromisoformat(row["respondido_en"]) if row["respondido_en"] else None,
    )


class InquiriesRepositorySQLite:
    def create(self, listing_id: UUID, remitente_user_id: UUID, data: dict) -> InquiryRow:
        inquiry = InquiryRow(
            id=uuid4(),
            listing_id=listing_id,
            remitente_user_id=remitente_user_id,
            respuesta=None,
            creado_en=datetime.now(timezone.utc),
            respondido_en=None,
            **data,
        )
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO inquiries"
                " (id, listing_id, remitente_user_id, nombre, email, telefono,"
                "  fecha_mudanza, mensaje, respuesta, creado_en, respondido_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(inquiry.id), str(inquiry.listing_id), str(inquiry.remitente_user_id),
                    inquiry.nombre, inquiry.email, inquiry.telefono,
                    inquiry.fecha_mudanza.isoformat() if inquiry.fecha_mudanza else None,
                    inquiry.mensaje, inquiry.respuesta, inquiry.creado_en.isoformat(),
                    inquiry.respondido_en.isoformat() if inquiry.respondido_en else None,
                ),
            )
        return inquiry

    def get(self, inquiry_id: UUID) -> InquiryRow | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM inquiries WHERE id = ?", (str(inquiry_id),)).fetchone()
        return _row_to_inquiry(row) if row else None

    def list_by_listing(self, listing_id: UUID) -> list[InquiryRow]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM inquiries WHERE listing_id = ? ORDER BY creado_en DESC",
                (str(listing_id),),
            ).fetchall()
        return [_row_to_inquiry(r) for r in rows]

    def list_by_user(self, user_id: UUID) -> list[InquiryRow]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM inquiries WHERE remitente_user_id = ? ORDER BY creado_en DESC",
                (str(user_id),),
            ).fetchall()
        return [_row_to_inquiry(r) for r in rows]

    def respond(self, inquiry_id: UUID, respuesta: str) -> InquiryRow | None:
        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            conn.execute(
                "UPDATE inquiries SET respuesta = ?, respondido_en = ? WHERE id = ?",
                (respuesta, now.isoformat(), str(inquiry_id)),
            )
            row = conn.execute("SELECT * FROM inquiries WHERE id = ?", (str(inquiry_id),)).fetchone()
        return _row_to_inquiry(row) if row else None


def count_inquiries_by_listing(listing_id: UUID) -> int:
    """Usada por ListingsRepositoryMemory.count_inquiries -- los avisos
    siguen en memoria pero las consultas que reciben ya no, así que ese
    conteo cruza a este módulo en vez de leer un dict local."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM inquiries WHERE listing_id = ?", (str(listing_id),)
        ).fetchone()
    return row["n"]


def _row_to_report(row: sqlite3.Row) -> ReportRow:
    return ReportRow(
        id=UUID(row["id"]),
        generado_por=UUID(row["generado_por"]),
        titulo=row["titulo"],
        destinatario_nombre=row["destinatario_nombre"],
        zone_id=row["zone_id"],
        dormitorios_bucket=row["dormitorios_bucket"],
        periodo=row["periodo"],
        secciones_incluidas=json.loads(row["secciones_incluidas"]),
        pdf_url=row["pdf_url"],
        generado_en=datetime.fromisoformat(row["generado_en"]),
    )


class ReportsRepositorySQLite:
    def create(self, row: ReportRow) -> ReportRow:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO reports"
                " (id, generado_por, titulo, destinatario_nombre, zone_id,"
                "  dormitorios_bucket, periodo, secciones_incluidas, pdf_url, generado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(row.id), str(row.generado_por), row.titulo, row.destinatario_nombre,
                    row.zone_id, row.dormitorios_bucket, row.periodo,
                    json.dumps(row.secciones_incluidas), row.pdf_url, row.generado_en.isoformat(),
                ),
            )
        return row

    def get(self, report_id: UUID) -> ReportRow | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (str(report_id),)).fetchone()
        return _row_to_report(row) if row else None

    def list_by_user(self, user_id: UUID) -> list[ReportRow]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE generado_por = ? ORDER BY generado_en DESC",
                (str(user_id),),
            ).fetchall()
        return [_row_to_report(r) for r in rows]
