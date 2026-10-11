FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY support_agent ./support_agent
RUN pip install --no-cache-dir '.[line]'
COPY knowledge ./knowledge

# 会話セッションとチケットは DATA_DIR と /root/.claude に保存される。永続ボリュームをマウントすること
ENV KNOWLEDGE_DIR=/app/knowledge DATA_DIR=/app/data
VOLUME ["/app/data", "/root/.claude"]

EXPOSE 8000
CMD ["sh", "-c", "uvicorn support_agent.line_bot:app --host 0.0.0.0 --port ${PORT:-8000}"]
