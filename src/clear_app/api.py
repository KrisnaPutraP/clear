"""FastAPI adapter for the existing CLEAR UI contract. Run one worker per store."""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from clear_app.bootstrap import create_clear, service_info
from clear_app.contract import Clear

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_id: NonBlank
    approver: NonBlank
    decision: Literal["approved", "rejected"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @model_validator(mode="after")
    def rejection_has_reason(self):
        if self.decision == "rejected" and not self.reason:
            raise ValueError("A rejection needs a reason.")
        return self


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver: NonBlank
    option: NonBlank | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @model_validator(mode="after")
    def own_course_has_note(self):
        self.note = self.note or None
        if self.option is None and not self.note:
            raise ValueError("A course outside the plan's options needs a note.")
        return self


def create_app(clear: Clear | None = None) -> FastAPI:
    """One service instance owns the background-run lock for every request."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.clear = clear if clear is not None else create_clear()
        try:
            yield
        finally:
            # Let an accepted action finish before shutting down this process.
            await asyncio.to_thread(app.state.clear.wait)

    app = FastAPI(title="CLEAR API", version="0.1.0", lifespan=lifespan)

    async def domain_error(request: Request, error: Exception):
        status = 404 if isinstance(error, LookupError) else 422 if isinstance(error, ValueError) else 409
        return JSONResponse(status_code=status, content={"detail": str(error)})

    for error_type in (LookupError, ValueError, RuntimeError, PermissionError):
        app.add_exception_handler(error_type, domain_error)

    @app.get("/health")
    def health(request: Request):
        return service_info(request.app.state.clear)

    @app.get("/events")
    def events(request: Request):
        service = request.app.state.clear
        with service.snapshot():
            return service.list_events()

    @app.get("/cases")
    def cases(request: Request):
        service = request.app.state.clear
        with service.snapshot():
            return service.list_cases()

    @app.post("/events/{event_id}", status_code=202)
    def send_event(event_id: str, request: Request):
        return {"case_id": request.app.state.clear.send_event(event_id)}

    @app.get("/cases/{case_id}")
    def case(case_id: str, request: Request):
        service = request.app.state.clear
        with service.snapshot():
            return service.get_case(case_id)

    @app.get("/cases/{case_id}/log")
    def log(case_id: str, request: Request, after_seq: Annotated[int, Query(ge=0)] = 0):
        service = request.app.state.clear
        with service.snapshot():
            # The contract returns an empty log for an unknown ID; HTTP returns 404.
            from clear_agents import caselog

            caselog.get_case(service.store, case_id)
            return service.get_case_log(case_id, after_seq)

    @app.post("/cases/{case_id}/decisions", status_code=202)
    def decide(case_id: str, body: Decision, request: Request):
        return request.app.state.clear.submit_decision(case_id=case_id, **body.model_dump())

    @app.post("/cases/{case_id}/resolution")
    def resolve(case_id: str, body: Resolution, request: Request):
        return request.app.state.clear.resolve_case(case_id=case_id, **body.model_dump())

    return app
