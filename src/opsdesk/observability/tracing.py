from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind
from sqlalchemy import Engine

from opsdesk.core.config import Settings


class Telemetry:
    def __init__(
        self,
        settings: Settings,
        *,
        span_exporter: SpanExporter | None = None,
    ) -> None:
        self.enabled = settings.otel_enabled
        self._sqlalchemy_instrumented = False
        self.provider: TracerProvider | None = None
        if not self.enabled:
            self.tracer = trace.get_tracer("opsdesk")
            return

        resource = Resource.create(
            {
                SERVICE_NAME: settings.service_name,
                SERVICE_VERSION: settings.version,
                "deployment.environment.name": settings.environment,
            }
        )
        self.provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_ratio)),
        )
        exporter = span_exporter or OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            timeout=settings.otel_export_timeout_seconds,
        )
        self.provider.add_span_processor(BatchSpanProcessor(exporter))
        self.tracer = self.provider.get_tracer("opsdesk.application", settings.version)

    def instrument(self, engine: Engine) -> None:
        if not self.enabled or self.provider is None:
            return
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.provider,
            enable_commenter=False,
        )
        self._sqlalchemy_instrumented = True

    @contextmanager
    def span(
        self, name: str, attributes: Mapping[str, str | int | float | bool] | None = None
    ) -> Iterator[Span]:
        with self.tracer.start_as_current_span(
            name,
            attributes=dict(attributes or {}),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield span

    @contextmanager
    def server_span(self, method: str, parent_context: Context | None) -> Iterator[Span]:
        with self.tracer.start_as_current_span(
            f"{method} unmatched",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield span

    def current_trace_id(self) -> str | None:
        if not self.enabled:
            return None
        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return None
        return trace.format_trace_id(context.trace_id)

    def force_flush(self, timeout_millis: int = 5_000) -> bool:
        if self.provider is None:
            return True
        return bool(self.provider.force_flush(timeout_millis=timeout_millis))

    def shutdown(self) -> None:
        if self._sqlalchemy_instrumented:
            SQLAlchemyInstrumentor().uninstrument()
            self._sqlalchemy_instrumented = False
        if self.provider is not None:
            self.provider.shutdown()
