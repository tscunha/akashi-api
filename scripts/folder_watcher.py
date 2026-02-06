#!/usr/bin/env python
"""
AKASHI MAM - Folder Watcher
Monitora pasta e faz ingest automático de arquivos.

Usage:
    python scripts/folder_watcher.py [pasta_ingest] [pasta_processados]

Defaults:
    pasta_ingest: D:\\AKASHI_INGEST
    pasta_processados: D:\\AKASHI_PROCESSED
"""

import os
import sys
import time
import shutil
import requests
from pathlib import Path
from datetime import datetime

# Fix encoding no Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Configuração
API_URL = "http://localhost:8000"
DEFAULT_INGEST_FOLDER = "D:\\AKASHI_INGEST"
DEFAULT_PROCESSED_FOLDER = "D:\\AKASHI_PROCESSED"
TENANT_CODE = "dev"
POLL_INTERVAL = 2  # segundos

# Extensões suportadas
SUPPORTED_EXTENSIONS = {
    # Video
    ".mp4", ".mov", ".avi", ".mkv", ".mxf", ".webm", ".wmv", ".flv",
    # Audio
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a",
    # Image
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
    # Document
    ".pdf", ".doc", ".docx",
}

# Cores ANSI
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def log(message, color=Colors.ENDC):
    """Log com timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.CYAN}[{timestamp}]{Colors.ENDC} {color}{message}{Colors.ENDC}")


def format_size(size_bytes):
    """Formata tamanho em bytes para formato legível."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def is_file_ready(filepath: Path, wait_time: float = 1.0) -> bool:
    """Verifica se o arquivo terminou de ser copiado."""
    try:
        initial_size = filepath.stat().st_size
        time.sleep(wait_time)
        final_size = filepath.stat().st_size
        return initial_size == final_size and final_size > 0
    except (OSError, FileNotFoundError):
        return False


def upload_file(filepath: Path) -> dict:
    """Faz upload do arquivo para a API."""
    url = f"{API_URL}/api/v1/ingest"

    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f)}
        data = {
            "title": filepath.stem,  # Nome sem extensão
            "tenant_code": TENANT_CODE,
        }

        response = requests.post(url, files=files, data=data, timeout=300)

    if response.status_code not in (200, 201):
        raise Exception(f"Upload failed: {response.status_code} - {response.text}")

    return response.json()


def process_jobs() -> dict:
    """Processa jobs pendentes."""
    url = f"{API_URL}/api/v1/jobs/process-pending?sync=true"
    response = requests.post(url, timeout=60)

    if response.status_code != 200:
        raise Exception(f"Process jobs failed: {response.status_code}")

    return response.json()


def check_api_health() -> bool:
    """Verifica se a API está rodando."""
    try:
        response = requests.get(f"{API_URL}/api/v1/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def watch_folder(ingest_folder: Path, processed_folder: Path):
    """Monitora pasta e processa arquivos novos."""

    # Header
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           AKASHI MAM - Folder Watcher                        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")

    log(f"Monitorando: {Colors.BOLD}{ingest_folder}{Colors.ENDC}")
    log(f"Destino processados: {processed_folder}")
    log(f"API: {API_URL}")
    print()
    log("Esperando arquivos...", Colors.YELLOW)
    print("─" * 64)

    # Verificar API
    if not check_api_health():
        log(f"[WARN] API nao esta respondendo em {API_URL}", Colors.RED)
        log("   Certifique-se que a API esta rodando!", Colors.YELLOW)
        print()

    processed_files = set()

    while True:
        try:
            # Listar arquivos na pasta de ingest
            for filepath in ingest_folder.iterdir():
                # Ignorar diretórios e arquivos já processados
                if filepath.is_dir() or filepath in processed_files:
                    continue

                # Verificar extensão
                if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                # Verificar se arquivo terminou de ser copiado
                if not is_file_ready(filepath):
                    continue

                file_size = filepath.stat().st_size
                log(f"[FILE] Detectado: {Colors.BOLD}{filepath.name}{Colors.ENDC} ({format_size(file_size)})")

                try:
                    # Upload
                    log("   [UPLOAD] Iniciado...", Colors.BLUE)
                    result = upload_file(filepath)
                    asset_id = result.get("asset_id", "?")
                    log(f"   [OK] Upload completo! Asset ID: {asset_id}", Colors.GREEN)

                    # Processar jobs
                    log("   [JOBS] Processando...", Colors.BLUE)
                    job_result = process_jobs()
                    log(f"   [OK] {job_result.get('message', 'Jobs processados')}", Colors.GREEN)

                    # Mover arquivo
                    dest_path = processed_folder / filepath.name

                    # Evitar sobrescrita
                    if dest_path.exists():
                        stem = filepath.stem
                        suffix = filepath.suffix
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        dest_path = processed_folder / f"{stem}_{timestamp}{suffix}"

                    shutil.move(str(filepath), str(dest_path))
                    log(f"   [MOVE] Movido para: {dest_path.name}", Colors.CYAN)

                    log(f"   {Colors.GREEN}{Colors.BOLD}[DONE] CONCLUIDO!{Colors.ENDC}")
                    print("─" * 64)

                    processed_files.add(filepath)

                except requests.RequestException as e:
                    log(f"   [ERROR] Erro de conexao: {e}", Colors.RED)
                    log("   Verifique se a API esta rodando!", Colors.YELLOW)

                except Exception as e:
                    log(f"   [ERROR] Erro: {e}", Colors.RED)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n")
            log("Watcher encerrado.", Colors.YELLOW)
            break


def main():
    # Argumentos
    ingest_folder = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INGEST_FOLDER)
    processed_folder = Path(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROCESSED_FOLDER)

    # Criar pastas se não existirem
    ingest_folder.mkdir(parents=True, exist_ok=True)
    processed_folder.mkdir(parents=True, exist_ok=True)

    # Iniciar watcher
    watch_folder(ingest_folder, processed_folder)


if __name__ == "__main__":
    main()
