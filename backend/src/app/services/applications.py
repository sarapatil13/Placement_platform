"""Application lifecycle service: create, withdraw, change status, timeline.

Encapsulates the eligibility snapshot and the append-only status history tables.
The eligibility check is ALWAYS re-run server-side at creation time — a client
can never self-declare eligibility.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionError_, ValidationError
from app.db.models import (
    APP_ACTIVE,
    APP_APPLIED,
    APP_TRANSITIONS,
    APP_WITHDRAWN,
    DRIVE_PUBLISHED,
    Application,
    ApplicationStatusHistory,
    PlacementDrive,
    Student,
)
from app.services.audit import AuditContext, record
from app.services.eligibility import evaluate_for_admission


class ApplicationService:
    def __init__(self, db: Session, actor_ctx: AuditContext | None = None) -> None:
        self.db = db
        self.ctx = actor_ctx

    # ------------------------------------------------------------------ #
    def create(
        self,
        *,
        student: Student,
        drive_id: str,
        resume_id: str | None = None,
        cover_note: str | None = None,
        resume_snapshot_text: str | None = None,
    ) -> Application:
        drive = self._get_published_drive(drive_id)
        _reject_duplicate(self.db, student.id, drive_id)
        _reject_after_deadline(drive)

        verdict = evaluate_for_admission(self.db, drive_id=drive_id, student=student)

        if not verdict.eligible:
            raise PermissionError__ineligible(verdict.reasons)

        application = Application(
            institution_id=student.institution_id,
            student_id=student.id,
            drive_id=drive.id,
            status=APP_APPLIED,
            eligibility_snapshot={
                "eligible": True,
                "definitive": verdict.definitive,
                "score": verdict.score,
                "reasons": verdict.reasons,
                "passed_rules": verdict.passed_rules,
                "evaluated_at": verdict.evaluated_at.isoformat(),
            },
            resume_id=resume_id,
            resume_snapshot_text=resume_snapshot_text,
            cover_note=cover_note,
        )
        self.db.add(application)
        self.db.flush()

        self.db.add(
            ApplicationStatusHistory(
                institution_id=student.institution_id,
                application_id=application.id,
                from_status=None,
                to_status=APP_APPLIED,
                changed_by=self.ctx.actor_id if self.ctx else None,
                changed_by_role=self.ctx.actor_role if self.ctx else None,
                note="Application submitted.",
                is_student_initiated=True,
            )
        )
        record(
            self.db,
            action="application.created",
            context=self.ctx,
            entity_type="application",
            entity_id=application.id,
            detail={
                "drive_id": drive.id,
                "student_id": student.id,
                "score": verdict.score,
            },
        )
        self.db.commit()
        self.db.refresh(application)
        return application

    # ------------------------------------------------------------------ #
    def change_status(
        self, application_id: str, new_status: str, note: str | None = None
    ) -> Application:
        application = self._get_application(application_id)
        old = application.status
        allowed = APP_TRANSITIONS.get(old, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot change application status from '{old}' to '{new_status}'.",
                code="invalid_status_transition",
            )
        if new_status == APP_WITHDRAWN:
            raise ValidationError(
                "Withdrawals are made by the student via the withdraw endpoint.",
                code="withdraw_via_endpoint",
            )

        application.status = new_status
        self.db.add(
            ApplicationStatusHistory(
                institution_id=application.institution_id,
                application_id=application.id,
                from_status=old,
                to_status=new_status,
                changed_by=self.ctx.actor_id if self.ctx else None,
                changed_by_role=self.ctx.actor_role if self.ctx else None,
                note=note,
                is_student_initiated=False,
            )
        )
        record(
            self.db,
            action="application.status_changed",
            context=self.ctx,
            entity_type="application",
            entity_id=application.id,
            detail={"from": old, "to": new_status},
        )
        self._notify_student(application, old, new_status, note)
        self.db.commit()
        self.db.refresh(application)
        return application

    def _notify_student(
        self, application: Application, old: str, new: str, note: str | None
    ) -> None:
        """Notify the applicant when the placement cell moves their application."""
        from app.services import notifications

        student = application.student
        if student is None or not student.user_id:
            return
        notifications.create(
            self.db,
            user_id=student.user_id,
            institution_id=application.institution_id,
            type=notifications.NOTIF_STATUS_CHANGE,
            title=f"Application status updated: {new.replace('_', ' ').title()}",
            body=(
                f"Your application for '{application.drive.title if application.drive else ''}' "
                f"moved from '{old.replace('_', ' ').title()}' to '{new.replace('_', ' ').title()}'."
                + (f" Note: {note}" if note else "")
            ),
            link=f"/applications/{application.id}",
            payload={"application_id": application.id, "from": old, "to": new},
        )
        self.db.flush()

    # ------------------------------------------------------------------ #
    def withdraw(self, application_id: str, student_id: str, reason: str | None) -> Application:
        application = self._get_application(application_id)
        if application.student_id != student_id:
            raise PermissionError_("You can only withdraw your own applications.")
        old = application.status
        if old not in APP_ACTIVE and old != APP_APPLIED:
            raise ValidationError(
                f"An application with status '{old}' can no longer be withdrawn.",
                code="terminal_status",
            )
        application.status = APP_WITHDRAWN
        application.withdrawn_reason = reason
        self.db.add(
            ApplicationStatusHistory(
                institution_id=application.institution_id,
                application_id=application.id,
                from_status=old,
                to_status=APP_WITHDRAWN,
                changed_by=self.ctx.actor_id if self.ctx else None,
                changed_by_role=self.ctx.actor_role if self.ctx else "student",
                note=reason or "Student withdrew application.",
                is_student_initiated=True,
            )
        )
        record(
            self.db,
            action="application.withdrawn",
            context=self.ctx,
            entity_type="application",
            entity_id=application.id,
            detail={"from": old, "student_id": student_id},
        )
        self.db.commit()
        self.db.refresh(application)
        return application

    # ------------------------------------------------------------------ #
    def _get_published_drive(self, drive_id: str) -> PlacementDrive:
        drive = self.db.get(PlacementDrive, drive_id)
        if drive is None:
            raise NotFoundError("Drive not found.")
        if drive.status != DRIVE_PUBLISHED:
            raise ValidationError(
                "This drive is not open for applications.",
                code="drive_not_open",
            )
        return drive

    def _get_application(self, application_id: str) -> Application:
        application = self.db.get(Application, application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return application


def _reject_duplicate(db: Session, student_id: str, drive_id: str) -> None:
    exists = (
        db.query(Application)
        .filter(
            Application.student_id == student_id,
            Application.drive_id == drive_id,
        )
        .first()
    )
    if exists:
        raise ConflictError(
            "You have already applied to this drive.",
            code="duplicate_application",
        )


def _reject_after_deadline(drive: PlacementDrive) -> None:
    apply_by = drive.apply_by
    if apply_by is None:
        return
    if apply_by.tzinfo is None:
        apply_by = apply_by.replace(tzinfo=UTC)
    if datetime.now(UTC) > apply_by:
        raise ValidationError(
            "The application deadline for this drive has passed.",
            code="deadline_passed",
        )


class PermissionError__ineligible(PermissionError_):
    """Marker subclass so the API layer can return the eligibility reasons body."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__(
            "This student does not currently meet the eligibility criteria.",
            code="not_eligible",
            extra={"reasons": reasons},
        )