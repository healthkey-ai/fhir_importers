from typing import Any, Dict, List, Literal, Optional, Union, Protocol, Type


class Span(Protocol):
    def set_attributes(self, attrs: Dict[str, Any]) -> None: ...
    def end(self) -> None: ...

class Tracer(Protocol):
    def start_trace(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span: ...
    def start_span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span: ...

class _NoopSpan:
    def set_attributes(self, attrs: Dict[str, Any]) -> None: ...
    def end(self) -> None: ...

class _NoopTracer:
    def start_trace(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span:
        return _NoopSpan()
    def start_span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span:
        return _NoopSpan()


class OpikTracer:
    """
    Tiny adapter so the client doesn't depend on Opik directly.
    Example:
        opik_client = Opik(project_name="RAG-Chat")
        tracer = OpikTracer(opik_client)
        client = OpenAiClientImplementation(openai_client, tracer)
    """
    def __init__(self, opik_client):
        self._opik = opik_client
        self._current_trace = None

    class _OpikSpanWrapper:
        def __init__(self, span):
            self._span = span
        def set_attributes(self, attrs: Dict[str, Any]) -> None:
            # Opik spans accept input/output/attributes; keep it simple with attributes
            self._span.update(attributes=attrs) if hasattr(self._span, "update") else None
        def end(self) -> None:
            if hasattr(self._span, "end"):
                self._span.end()

    def start_trace(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span:
        trace = self._opik.trace(name=name, input=attrs or {})
        self._current_trace = trace
        return self._OpikSpanWrapper(trace)

    def start_span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Span:
        parent = self._current_trace or self._opik  # if no trace, create standalone span
        span = parent.span(name=name, input=attrs or {})
        return self._OpikSpanWrapper(span)
