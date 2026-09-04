from fastapi import APIRouter

from app.api.v1 import (
    auth,
    billing,
    captions,
    health,
    jobs,
    media,
    projects,
    providers,
    render,
    research,
    scenes,
    scripts,
    timeline,
    usage,
    voiceovers,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(research.router, prefix="/projects/{project_id}/research", tags=["research"])
api_router.include_router(scripts.router, prefix="/projects/{project_id}/script", tags=["scripts"])
api_router.include_router(scenes.router, prefix="/projects/{project_id}/scenes", tags=["scenes"])
api_router.include_router(voiceovers.router, tags=["voiceovers"])
api_router.include_router(captions.router, prefix="/projects/{project_id}/captions", tags=["captions"])
api_router.include_router(timeline.router, prefix="/projects/{project_id}/timeline", tags=["timeline"])
api_router.include_router(render.router, tags=["rendering"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
