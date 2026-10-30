FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY sql ./sql
RUN mkdir -p data/raw output
CMD ["python", "-m", "pipeline.run", "all", "--orders", "5000"]
