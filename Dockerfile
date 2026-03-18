FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lexai/backend/ .
COPY start.sh .
RUN chmod +x start.sh
RUN mkdir -p /app/data/historico /app/chroma_db
EXPOSE 8000
CMD ["bash", "start.sh"]
