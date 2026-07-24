FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

# Apply migrations before serving so any deploy of this image (compose or a bare
# `docker run`) brings the schema to head first. Without it the app starts but
# every DB-backed route 500s on "relation does not exist" the moment a migration
# is unshipped — e.g. the model_response_cache table the replay cache reads.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
