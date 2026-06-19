"""Export API (spec §21)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.db.database import get_db
from app.evaluation.export_builder import export_all

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.post("/run")
def run_export(db: DbSession = Depends(get_db)):
    counts = export_all(db)
    return {"exportDir": str(settings.export_dir), "files": counts}


@router.get("/download/{filename}")
def download(filename: str):
    if "/" in filename or ".." in filename or not filename.endswith(".jsonl"):
        raise HTTPException(400, "invalid filename")
    path = settings.export_dir / filename
    if not path.exists():
        raise HTTPException(404, "file not found — run POST /api/exports/run first")
    return FileResponse(path, media_type="application/jsonl", filename=filename)
