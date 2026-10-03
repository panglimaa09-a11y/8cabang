FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/srv/app

WORKDIR /srv/app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# backend/app becomes the `app` package so `uvicorn app.main:app` resolves.
COPY backend/app ./app
# index.html lives at the repo root (per PRD structure); frontend/ holds css/js/assets.
COPY index.html ./index.html
COPY frontend ./frontend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
