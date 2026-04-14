from fastapi import APIRouter

from app.api.v1.cotizaciones import router as cotizaciones_router
from app.api.v1.history import router as history_router

router = APIRouter(prefix="/api/v1")

router.include_router(cotizaciones_router)
router.include_router(history_router)
