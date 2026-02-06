#!/usr/bin/env python
"""
AKASHI MAM - Teste de Fluxo Completo
Testa o pipeline de ingest end-to-end.
"""

import os
import sys
import time
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

# Config
API_URL = "http://localhost:8000"
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "akashi_mam",
    "user": "akashi",
    "password": "akashi_dev_2025",
}

def test_api():
    """Testa API health."""
    print("1. Testando API...")
    try:
        r = requests.get(f"{API_URL}/api/v1/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"   API OK: {data}")
            return True
        else:
            print(f"   ERRO: Status {r.status_code}")
            return False
    except Exception as e:
        print(f"   ERRO: {e}")
        return False


def test_db():
    """Testa conexão com DB."""
    print("2. Testando DB...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as cnt FROM assets")
        result = cur.fetchone()
        print(f"   DB OK: {result['cnt']} assets")
        conn.close()
        return True
    except Exception as e:
        print(f"   ERRO: {e}")
        return False


def test_upload():
    """Testa upload de arquivo."""
    print("3. Testando Upload...")

    # Criar arquivo de teste
    test_file = Path("test_video.txt")
    test_file.write_text("Conteudo de teste para simular video")

    try:
        with open(test_file, "rb") as f:
            files = {"file": ("test_video.mp4", f)}
            data = {"title": "Video de Teste", "tenant_code": "dev"}

            r = requests.post(
                f"{API_URL}/api/v1/ingest",
                files=files,
                data=data,
                timeout=30
            )

        if r.status_code in (200, 201):
            result = r.json()
            print(f"   Upload OK!")
            print(f"   Asset ID: {result.get('asset_id')}")
            print(f"   Status: {result.get('status')}")
            print(f"   Jobs: {len(result.get('jobs', []))}")
            return result.get('asset_id')
        else:
            print(f"   ERRO: {r.status_code} - {r.text}")
            return None

    except Exception as e:
        print(f"   ERRO: {e}")
        return None
    finally:
        test_file.unlink(missing_ok=True)


def test_process_jobs():
    """Testa processamento de jobs."""
    print("4. Processando Jobs...")
    try:
        r = requests.post(f"{API_URL}/api/v1/jobs/process-pending?sync=true", timeout=60)
        if r.status_code == 200:
            result = r.json()
            print(f"   Jobs OK: {result.get('message')}")
            return True
        else:
            print(f"   ERRO: {r.status_code}")
            return False
    except Exception as e:
        print(f"   ERRO: {e}")
        return False


def test_list_assets():
    """Testa listagem de assets."""
    print("5. Listando Assets...")
    try:
        r = requests.get(f"{API_URL}/api/v1/assets", timeout=10)
        if r.status_code == 200:
            result = r.json()
            print(f"   Total: {result.get('total')} assets")
            for item in result.get('items', [])[:3]:
                print(f"   - {item['title']}: {item['status']}")
            return True
        else:
            print(f"   ERRO: {r.status_code}")
            return False
    except Exception as e:
        print(f"   ERRO: {e}")
        return False


def main():
    print("=" * 50)
    print("  AKASHI MAM - Teste de Fluxo Completo")
    print("=" * 50)
    print()

    results = []

    results.append(("API", test_api()))
    results.append(("DB", test_db()))

    asset_id = test_upload()
    results.append(("Upload", asset_id is not None))

    if asset_id:
        results.append(("Jobs", test_process_jobs()))

    results.append(("List", test_list_assets()))

    print()
    print("=" * 50)
    print("  RESULTADOS")
    print("=" * 50)

    all_ok = True
    for name, ok in results:
        status = "OK" if ok else "FALHOU"
        print(f"  {name}: {status}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("  >>> TODOS OS TESTES PASSARAM! <<<")
    else:
        print("  >>> ALGUNS TESTES FALHARAM <<<")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
