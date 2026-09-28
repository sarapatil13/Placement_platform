"""Aggregate API router: /api/v1/*"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, applications, auth, drives, notifications, resumes, students

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(students.router)
api_router.include_router(drives.router)
api_router.include_router(resumes.router)
api_router.include_router(applications.router)
api_router.include_router(notifications.router)
api_router.include_router(admin.router)