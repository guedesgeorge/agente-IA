# ⚖️ LexAI — Agente Jurídico com RAG

Sistema de IA jurídica com base vetorial treinada nos processos do escritório.

## Arquitetura

```
┌──────────────┐     HTTP      ┌─────────────────────────────────┐
│  Frontend    │ ────────────► │  Backend FastAPI                 │
│  index.html  │               │                                  │
└──────────────┘               │  /upload  → Indexa documento     │
                               │  /chat    → RAG + Claude         │
                               │  /documents → Lista base         │
                               └────────────┬────────────────────┘
                                            │
                              ┌─────────────▼──────────────┐
                              │  ChromaDB (local)           │
                              │  Vetores dos processos       │
                              │  Embeddings multilíngues     │
                              └────────────────────────────┘
```

## Como Funciona o RAG

1. **Ingestão**: Advogado envia um PDF/DOCX → texto extraído → dividido em chunks → embeddings gerados → salvos no ChromaDB
2. **Consulta**: Advogado faz pergunta → embedding da pergunta → busca semântica nos chunks → top-6 chunks relevantes → enviados ao Claude como contexto
3. **Resposta**: Claude responde citando os documentos do escritório que embasaram a resposta

---

## Instalação e Setup

### 1. Pré-requisitos
- Python 3.10+
- pip

### 2. Instalar dependências

```bash
cd backend
pip install -r requirements.txt
```

> Na primeira execução, o modelo de embeddings (~120MB) será baixado automaticamente.

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env e coloque sua chave da Anthropic
```

### 4. Rodar o servidor

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

O backend estará disponível em: http://localhost:8000
Documentação automática: http://localhost:8000/docs

### 5. Abrir o frontend

Basta abrir `frontend/index.html` no navegador.

Na primeira abertura, clique em **"Configurar Backend"** e informe `http://localhost:8000`.

---

## Indexar Documentos

### Via Interface Web
1. Abra o frontend → aba "Base de Docs"
2. Clique na zona de upload
3. Selecione PDFs, DOCXs ou TXTs dos processos
4. Aguarde a indexação (aparece o nº de chunks)

### Via API (em lote)
```bash
# Indexar um único arquivo
curl -X POST http://localhost:8000/upload \
  -F "file=@processo_trabalhista.pdf"

# Script para indexar pasta inteira (Python)
python scripts/batch_ingest.py ./pasta_processos/
```

---

## Estrutura do Projeto

```
lexai/
├── backend/
│   ├── main.py           # API FastAPI (rotas)
│   ├── rag_engine.py     # Motor RAG (ingestão + busca + geração)
│   ├── requirements.txt
│   ├── .env.example
│   └── chroma_db/        # Base vetorial (criada automaticamente)
├── frontend/
│   └── index.html        # Interface web completa
└── README.md
```

---

## Deploy em Produção

### Opção 1: VPS (Recomendado para escritório)
```bash
# Instalar dependências de sistema
sudo apt install python3-pip nginx

# Rodar com PM2 ou systemd
pip install gunicorn
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Opção 2: Docker
```bash
docker build -t lexai-backend .
docker run -d -p 8000:8000 -v ./chroma_db:/app/chroma_db \
  -e ANTHROPIC_API_KEY=sk-ant-... lexai-backend
```

### Opção 3: Railway / Render (nuvem simples)
1. Suba o repositório no GitHub
2. Conecte no Railway.app ou Render.com
3. Configure a variável `ANTHROPIC_API_KEY`
4. O ChromaDB persistirá em volume montado

---

## Evoluções Futuras

- [ ] Autenticação JWT por advogado
- [ ] Múltiplos escritórios (multi-tenant)
- [ ] OCR para processos escaneados (Tesseract)
- [ ] Geração de DOCX formatado das peças
- [ ] Integração com sistemas jurídicos (PJe, eSAJ)
- [ ] Dashboard de analytics das consultas
