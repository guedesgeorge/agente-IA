"""
Script para indexar em lote todos os documentos de uma pasta.
Uso: python batch_ingest.py ./pasta_com_processos/
"""

import sys
import os
import requests
from pathlib import Path

BACKEND_URL = os.getenv("LEXAI_BACKEND", "http://localhost:8000")
ALLOWED = {".pdf", ".docx", ".txt", ".doc"}


def ingest_folder(folder: str):
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"❌ Pasta não encontrada: {folder}")
        sys.exit(1)

    files = [f for f in folder_path.rglob("*") if f.suffix.lower() in ALLOWED]
    print(f"📂 Encontrados {len(files)} documentos em '{folder}'")
    print(f"🔗 Backend: {BACKEND_URL}\n")

    success, failed = 0, 0
    for i, file in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Indexando: {file.name}...", end=" ", flush=True)
        try:
            with open(file, "rb") as f:
                r = requests.post(
                    f"{BACKEND_URL}/upload",
                    files={"file": (file.name, f, "application/octet-stream")},
                    timeout=60
                )
            if r.ok:
                data = r.json()
                print(f"✅ {data['chunks']} chunks")
                success += 1
            else:
                print(f"❌ HTTP {r.status_code}")
                failed += 1
        except Exception as e:
            print(f"❌ {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"✅ Indexados com sucesso: {success}")
    print(f"❌ Falhas: {failed}")
    print(f"📚 Total na base: verifique em {BACKEND_URL}/documents")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python batch_ingest.py <pasta>")
        print("Exemplo: python batch_ingest.py ./processos/")
        sys.exit(1)
    ingest_folder(sys.argv[1])
