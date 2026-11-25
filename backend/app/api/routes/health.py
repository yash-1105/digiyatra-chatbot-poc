from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.schemas.chat import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    st = request.app.state
    index_info: dict = {"loaded": False}
    if getattr(st, "index_meta", None):
        m = st.index_meta
        index_info = {
            "loaded": True,
            "documents": m.get("document_count"),
            "chunks": st.retriever.chunk_count if getattr(st, "retriever", None) else m.get("chunk_count"),
            "embedder": m.get("embedder"),
            "updated_at": m.get("updated_at"),
            "official_records": m.get("official_records", 0),
            "publication_id": m.get("publication_id"),
        }
    llm = {"provider": "sarvam", "model": st.settings.sarvam_chat_model, "configured": st.llm.configured}
    # Label only (never the URL/path): lets test scripts refuse to write into the primary analytics DB.
    database = {
        "migrated": st.db.is_migrated(),
        "label": "synthetic" if "synthetic" in st.settings.database_url else "primary",
    }
    ok = index_info["loaded"] and llm["configured"]
    return HealthResponse(status="ok" if ok else "degraded", version=__version__, index=index_info, llm=llm, database=database)
