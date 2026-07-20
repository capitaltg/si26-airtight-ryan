from fastapi import FastAPI

app = FastAPI(title="Airtight")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
