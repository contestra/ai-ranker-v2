from fastapi import APIRouter
from ..deps_vertex import init_vertex

router = APIRouter()

@router.get("/preflight/vertex")
def vertex_preflight():
    try:
        info = init_vertex()
        return {"ready": True, **info}
    except Exception as e:
        return {"ready": False, "error": str(e)}