from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import content as content_router
from app.api import sessions as sessions_router
from app.content.loader import load_content


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load and validate authored content once at startup. A malformed file raises
    # here and crashes the app (fail-fast) rather than serving on partial content.
    app.state.content = load_content()
    yield


app = FastAPI(title="Airtight", lifespan=lifespan)

app.include_router(sessions_router.router)
app.include_router(content_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
