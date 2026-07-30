FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir requests

COPY enhancer.py .
ENV VAULT_PATH=/vault
ENV OLLAMA_URL=http://obsidian-ollama:11434
ENV MODEL=phi4
ENV PYTHONUNBUFFERED=1

CMD ["python3", "enhancer.py"]
