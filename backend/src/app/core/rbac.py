"""RBAC matrix: the single source of truth for who may do what.

Every protected route declares a permission; `has_permission` is the only check
used by dependencies. Permissions are institution-scoped implicitly: a caller may
only act on rows belonging to their own institution, which is enforced separately
by `app.api.deps.enforce_institution_scope`.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    # --- self-service ---
    READ_OWN_PROFILE = "profile:read_own"
    UPDATE_OWN_CONTACT_DETAILS = "profile:update_own_contact"
    READ_OWN_RESUMES = "resume:read_own"
    MANAGE_OWN_RESUMES = "resume:manage_own"
    READ_OWN_APPLICATIONS = "application:read_own"
    CREATE_OWN_APPLICATION = "application:create_own"
    WITHDRAW_OWN_APPLICATION = "application:withdraw_own"
    READ_OWN_NOTIFICATIONS = "notification:read_own"
    VIEW_OPPORTUNITIES = "drive:view"
    RUN_OWN_ANALYSIS = "analysis:run_own"

    # --- placement cell / admin ---
    READ_ANY_STUDENT = "student:read_any"
    IMPORT_STUDENTS = "student:import"
    UPDATE_INSTITUTIONAL_STUDENT_FIELDS = "student:update_institutional_fields"
    DEACTIVATE_STUDENT = "student:deactivate"
    MANAGE_DEPARTMENTS = "department:manage"
    MANAGE_COMPANIES = "company:manage"
    MANAGE_DRIVES = "drive:manage"
    PUBLISH_DRIVE = "drive:publish"
    MANAGE_ELIGIBILITY_CRITERIA = "eligibility:manage"
    UPLOAD_JD = "jd:upload"
    CONFIRM_AI_EXTRACTION = "jd:confirm_extraction"
    READ_ALL_APPLICATIONS = "application:read_all"
    UPDATE_APPLICATION_STATUS = "application:update_status"
    READ_ANALYTICS = "analytics:read"
    READ_AUDIT_LOG = "audit:read"
    MANAGE_USERS = "user:manage"
    READ_INSTITUTION_SETTINGS = "institution:read_settings"


STUDENT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_CONTACT_DETAILS,
        Permission.READ_OWN_RESUMES,
        Permission.MANAGE_OWN_RESUMES,
        Permission.READ_OWN_APPLICATIONS,
        Permission.CREATE_OWN_APPLICATION,
        Permission.WITHDRAW_OWN_APPLICATION,
        Permission.READ_OWN_NOTIFICATIONS,
        Permission.VIEW_OPPORTUNITIES,
        Permission.RUN_OWN_ANALYSIS,
    }
)

PLACEMENT_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        # Admins can also read their own profile and the opportunity catalogue.
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_CONTACT_DETAILS,
        Permission.READ_OWN_RESUMES,
        Permission.MANAGE_OWN_RESUMES,
        Permission.READ_OWN_APPLICATIONS,
        Permission.READ_OWN_NOTIFICATIONS,
        Permission.VIEW_OPPORTUNITIES,
        Permission.RUN_OWN_ANALYSIS,
        Permission.READ_ANY_STUDENT,
        Permission.IMPORT_STUDENTS,
        Permission.UPDATE_INSTITUTIONAL_STUDENT_FIELDS,
        Permission.DEACTIVATE_STUDENT,
        Permission.MANAGE_DEPARTMENTS,
        Permission.MANAGE_COMPANIES,
        Permission.MANAGE_DRIVES,
        Permission.PUBLISH_DRIVE,
        Permission.MANAGE_ELIGIBILITY_CRITERIA,
        Permission.UPLOAD_JD,
        Permission.CONFIRM_AI_EXTRACTION,
        Permission.READ_ALL_APPLICATIONS,
        Permission.UPDATE_APPLICATION_STATUS,
        Permission.READ_ANALYTICS,
        Permission.READ_AUDIT_LOG,
        Permission.READ_INSTITUTION_SETTINGS,
    }
)

SUPER_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(
    PLACEMENT_ADMIN_PERMISSIONS | {Permission.MANAGE_USERS}
)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "student": STUDENT_PERMISSIONS,
    "placement_admin": PLACEMENT_ADMIN_PERMISSIONS,
    "super_admin": SUPER_ADMIN_PERMISSIONS,
}


def permissions_for(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: Permission | str) -> bool:
    """True when the role holds the permission. Unknown roles get nothing."""
    try:
        perm = Permission(permission)
    except ValueError:
        return False
    return perm in permissions_for(role)


def is_admin(role: str) -> bool:
    return role in {"placement_admin", "super_admin"}
