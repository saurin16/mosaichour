FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY mosaichour ./mosaichour
COPY static ./static
RUN pip install --no-cache-dir .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn mosaichour.main:app --host 0.0.0.0 --port ${PORT}"]
