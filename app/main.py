from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .routers import (
    admin_nodes,
    admin_users,
    auth,
    dictionaries,
    nodes,
    operations,
    public,
    shipments,
)
from . import web

def feature():
    # GOOD CODE
    return False

app = FastAPI(
    title="ИСУДО — Информационная система управления доставкой отправлений",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

register_exception_handlers(app)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(web.router)

PREFIX = "/api/v1"
app.include_router(public.router, prefix=PREFIX)
app.include_router(auth.router, prefix=PREFIX)
app.include_router(dictionaries.router, prefix=PREFIX)
app.include_router(nodes.router, prefix=PREFIX)
app.include_router(shipments.router, prefix=PREFIX)
app.include_router(operations.router, prefix=PREFIX)
app.include_router(admin_users.router, prefix=PREFIX)
app.include_router(admin_nodes.router, prefix=PREFIX)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}