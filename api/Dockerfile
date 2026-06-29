# CarDuka API (PRIVATE service). Python 3.12 for ChromaDB / ONNX compatibility.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Bake Chroma's ONNX all-MiniLM-L6-v2 model into the image without pulling
# PyTorch/CUDA. Invoking the function once populates Chroma's model cache.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; \
    DefaultEmbeddingFunction()(['warm cache'])"

COPY app ./app

EXPOSE 8000
# Railway provides $PORT; default 8000 for local.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
