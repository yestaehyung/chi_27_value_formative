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


@router.get("/archive")
def download_archive(db: DbSession = Depends(get_db)):
    """전체 데이터 ZIP 한 번에 — export_all을 새로 돌려 모든 테이블 JSONL을 묶는다.
    관리자 페이지 '전체 데이터 다운로드' 버튼용 (study 모드에선 연구 키 게이트 뒤)."""
    import io
    import zipfile
    from datetime import datetime, timezone

    from fastapi.responses import Response

    counts = export_all(db)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in counts:
            p = settings.export_dir / name
            if p.exists():
                z.write(p, arcname=name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vc_export_{stamp}.zip"'},
    )


@router.get("/download/{filename}")
def download(filename: str):
    if "/" in filename or ".." in filename or not filename.endswith(".jsonl"):
        raise HTTPException(400, "invalid filename")
    path = settings.export_dir / filename
    if not path.exists():
        raise HTTPException(404, "file not found — run POST /api/exports/run first")
    return FileResponse(path, media_type="application/jsonl", filename=filename)
