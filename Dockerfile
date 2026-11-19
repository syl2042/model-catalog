FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /app/output
VOLUME /app/output
ENTRYPOINT ["aurora-model-catalog"]
CMD ["sync"]
