"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pos_inventory.core.errors import DomainError


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": str(exc) or exc.code},
        )


def _register_routers(app: FastAPI) -> None:
    # Routers are imported lazily so unit tests for individual routers can
    # exercise app.include_router(router) on a fresh app.
    from pos_inventory.api.v1 import (
        purchase_orders,
        receipts,
        serials,
        inventory,
        pos_intake,
        returns,
        rmas,
        counts,
        locations,
        transfers,
        config,
    )

    for mod in (
        purchase_orders,
        receipts,
        serials,
        inventory,
        pos_intake,
        returns,
        rmas,
        counts,
        locations,
        transfers,
        config,
    ):
        app.include_router(mod.router, prefix="/v1")


def create_app() -> FastAPI:
    app = FastAPI(title="POS Inventory", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_error_handlers(app)
    _register_routers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
