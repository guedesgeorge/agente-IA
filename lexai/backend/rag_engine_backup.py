"""
LexRAGEngine — Motor RAG para documentos jurídicos
- Ingere PDFs, DOCX e TXT
- Gera embeddings com sentence-transformers
- Armazena em ChromaDB (local)
- Recupera contexto e gera resposta com Claude
"""

import os
import uuid
import hashlib
import asyncio
from typing import Optional
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

import anthropic

# Extratores de texto
import PyPDF2
import docx
import io


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """Você é LexAI, um agente jurídico inteligente especializado no direito brasileiro.
Você tem acesso a uma base de conhecimento com processos e documentos reais do escritório.

Ao responder:
- Cite sempre os trechos relevantes encontrados na base de documentos (indicando o nome do arquivo)
- Baseie-se na legislação brasileira: CLT, CPC, CC, CF, CDC e leis especiais
- Use linguagem técnica jurídica formal
- Cite artigos de lei quando aplicável (ex: "art. 7º, XVI da CF/88")
- Ao redigir peças, siga a estrutura formal completa

CONTEXTO DA BASE DE DOCUMENTOS:
{context}
"""

MODE_PREFIXES = {
    "consulta": "",
    "peticao": (
        "Redija uma peça processual completa e formal, com: qualificação das partes, "
        "exposição dos fatos, fundamentos jurídicos (com artigos de lei), pedidos e encerramento. "
        "Solicitação: "
    ),
    "analise": (
        "Analise juridicamente o seguinte, identificando: riscos legais, cláusulas problemáticas, "
        "fundamentos aplicáveis e recomendações práticas. Objeto de análise: "
    ),
}


class LexRAGEngine:
    def __init__(self, db_path: str = "./chroma_db"):
        """Inicializa ChromaDB e cliente Anthropic."""
        self.client_chroma = chromadb.PersistentClient(path=db_path)
        self.client_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Embedding function — usa modelo local multilíngue (gratuito)
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )

        # Coleção principal de chunks de documentos
        self.collection = self.client_chroma.get_or_create_collection(
            name="lexai_docs",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

        # Coleção de metadados de documentos (para listagem)
        self.meta_collection = self.client_chroma.get_or_create_collection(
            name="lexai_meta"
        )

    # ── INGESTÃO ─────────────────────────────────────────

    def ingest_document(self, content: bytes, filename: str, file_type: str) -> dict:
        """Extrai texto, divide em chunks e indexa no ChromaDB."""
        text = self._extract_text(content, file_type)
        if not text.strip():
            raise ValueError("Não foi possível extrair texto do documento.")

        chunks = self._split_chunks(text, chunk_size=800, overlap=100)
        doc_id = hashlib.md5(content).hexdigest()[:12]

        # Salva chunks com metadados
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "ingested_at": datetime.now().isoformat(),
            }
            for i in range(len(chunks))
        ]

        self.collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas
        )

        # Salva metadado do documento (para listagem)
        self.meta_collection.upsert(
            ids=[doc_id],
            documents=[filename],
            metadatas=[{
                "filename": filename,
                "file_type": file_type,
                "chunks": len(chunks),
                "ingested_at": datetime.now().isoformat(),
                "size_chars": len(text)
            }]
        )

        return {"doc_id": doc_id, "chunks": len(chunks)}

    def _extract_text(self, content: bytes, file_type: str) -> str:
        """Extrai texto de PDF, DOCX ou TXT."""
        if file_type == ".pdf":
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            return "\n\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        elif file_type in (".docx", ".doc"):
            doc = docx.Document(io.BytesIO(content))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif file_type == ".txt":
            return content.decode("utf-8", errors="ignore")
        return ""

    def _split_chunks(self, text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
        """Divide texto em chunks com overlap para não perder contexto entre partes."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i: i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return [c for c in chunks if len(c.strip()) > 50]

    # ── RECUPERAÇÃO ──────────────────────────────────────

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Busca semântica: retorna os k chunks mais relevantes."""
        if self.collection.count() == 0:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=min(k, self.collection.count())
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            output.append({
                "text": doc,
                "filename": meta.get("filename", ""),
                "doc_id": meta.get("doc_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "distance": results["distances"][0][i] if "distances" in results else None,
            })
        return output

    # ── GERAÇÃO ──────────────────────────────────────────

    async def answer(
        self,
        question: str,
        mode: str = "consulta",
        history: list = [],
        use_kb: bool = True,
        k: int = 6
    ) -> tuple[str, list[dict]]:
        """
        Pipeline RAG completo:
        1. Busca contexto relevante
        2. Monta prompt com contexto
        3. Gera resposta com Claude
        """
        sources = []
        context_str = "Nenhum documento relevante encontrado na base."

        if use_kb and self.collection.count() > 0:
            sources = self.search(question, k=k)
            if sources:
                context_str = "\n\n---\n\n".join(
                    f"[Arquivo: {s['filename']} | Trecho {s['chunk_index']+1}]\n{s['text']}"
                    for s in sources
                )

        system = SYSTEM_PROMPT.format(context=context_str)

        # Monta histórico de mensagens
        messages = []
        for h in history[-10:]:  # últimas 10 trocas para não estourar contexto
            messages.append({"role": h["role"], "content": h["content"]})

        # Adiciona prefixo de modo na pergunta atual
        prefix = MODE_PREFIXES.get(mode, "")
        messages.append({"role": "user", "content": prefix + question})

        # Chama Claude (run em thread para não bloquear o event loop)
        response = await asyncio.to_thread(
            self._call_claude, system, messages
        )

        return response, sources

    def _call_claude(self, system: str, messages: list) -> str:
        response = self.client_anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system,
            messages=messages
        )
        return response.content[0].text

    # ── UTILITÁRIOS ──────────────────────────────────────

    def count_documents(self) -> int:
        return self.meta_collection.count()

    def list_documents(self) -> list[dict]:
        if self.meta_collection.count() == 0:
            return []
        results = self.meta_collection.get()
        docs = []
        for i, doc_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            docs.append({"doc_id": doc_id, **meta})
        return docs

    def delete_document(self, doc_id: str):
        """Remove todos os chunks de um documento da base."""
        # Remove chunks
        results = self.collection.get(where={"doc_id": doc_id})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
        # Remove metadado
        self.meta_collection.delete(ids=[doc_id])
