from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.consumer import OrbitalForwarder, RabbitConsumer
from app.metadata import MetadataValidationError, metadata_from_http
from app.publisher import PublishError, RabbitPublisher, UnroutablePublishError
from app.sap_xml import SapXmlSerializationError, sap_json_to_xml


LOGGER = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    publisher: Any | None = None,
    consumer: Any | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    publisher = publisher or RabbitPublisher(settings)
    if consumer is None:
        forwarder = OrbitalForwarder(
            settings.orbital_sap_url,
            settings.orbital_timeout,
        )
        consumer = RabbitConsumer(settings, forwarder)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.consumer_enabled:
            consumer.start()
        try:
            yield
        finally:
            if settings.consumer_enabled:
                consumer.stop()
            publisher.close()

    app = FastAPI(
        title="Customer Account Rabbit Bridge",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.publisher = publisher
    app.state.consumer = consumer

    @app.get("/health")
    async def health() -> JSONResponse:
        if not settings.consumer_enabled:
            return JSONResponse(
                {"status": "ok", "consumer": {"enabled": False}},
                status_code=200,
            )
        snapshot = consumer.health_snapshot()
        healthy = bool(snapshot.get("running") and snapshot.get("connected"))
        return JSONResponse(
            {
                "status": "ok" if healthy else "degraded",
                "consumer": {"enabled": True, **snapshot},
            },
            status_code=200 if healthy else 503,
        )

    @app.post("/publish", status_code=202)
    async def publish(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"application/json", "application/xml", "text/xml"}:
            return JSONResponse(
                {
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": (
                        "Content-Type must be application/json, application/xml, "
                        "or text/xml"
                    ),
                },
                status_code=415,
            )

        body = await request.body()
        if not body.strip():
            return JSONResponse(
                {"code": "EMPTY_BODY", "message": "Request body is required"},
                status_code=400,
            )

        if content_type == "application/json":
            try:
                body = sap_json_to_xml(body)
            except SapXmlSerializationError as exc:
                return JSONResponse(
                    {"code": "INVALID_SAP_PAYLOAD", "message": str(exc)},
                    status_code=400,
                )

        try:
            metadata = metadata_from_http(
                request.headers,
                routing_key=settings.adobe_to_sap_routing_key,
                default_schema=settings.expected_schema,
                default_event_type=settings.event_type,
            )
        except MetadataValidationError as exc:
            return JSONResponse(
                {"code": exc.code, "message": str(exc)},
                status_code=400,
            )

        try:
            await run_in_threadpool(
                publisher.publish,
                body,
                metadata,
                settings.adobe_to_sap_routing_key,
            )
        except UnroutablePublishError as exc:
            return JSONResponse(
                {"code": "UNROUTABLE", "message": str(exc)},
                status_code=503,
            )
        except PublishError as exc:
            return JSONResponse(
                {"code": "PUBLISH_FAILED", "message": str(exc)},
                status_code=503,
            )

        return JSONResponse(
            {
                "status": "published",
                "message_id": metadata.message_id,
                "correlation_id": metadata.correlation_id,
                "routing_key": settings.adobe_to_sap_routing_key,
            },
            status_code=202,
        )

    return app


settings = Settings.from_env()
app = create_app(settings)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(app, host=settings.http_host, port=settings.bridge_port)
