FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/ui ./ui
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app
COPY backend ./backend
COPY run.py .
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir data && chown -R app:app /app
USER app
EXPOSE 5001
HEALTHCHECK --interval=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health/ready')"
CMD ["gunicorn", "--workers", "1", "--threads", "20", "--bind", "0.0.0.0:5001", "run:app"]
