#!/usr/bin/env python
"""
AKASHI MAM - Database Monitor
Exibe status do banco de dados em tempo real.

Usage:
    python scripts/db_monitor.py
"""

import os
import sys
import time
from datetime import datetime

# Fix encoding no Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor

# Configuração do banco
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "akashi_mam",
    "user": "akashi",
    "password": "akashi_dev_2025",
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


def clear_screen():
    """Limpa a tela do terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def get_asset_stats(cursor):
    """Obtém estatísticas de assets."""
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'available') as available,
            COUNT(*) FILTER (WHERE status = 'processing') as processing,
            COUNT(*) FILTER (WHERE status = 'ingesting') as ingesting,
            COUNT(*) FILTER (WHERE status = 'deleted') as deleted
        FROM assets
        WHERE deleted_at IS NULL
    """)
    return cursor.fetchone()


def get_job_stats(cursor):
    """Obtém estatísticas de jobs."""
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'completed') as completed,
            COUNT(*) FILTER (WHERE status = 'pending') as pending,
            COUNT(*) FILTER (WHERE status = 'processing') as processing,
            COUNT(*) FILTER (WHERE status = 'failed') as failed
        FROM ingest_jobs
    """)
    return cursor.fetchone()


def get_recent_assets(cursor, limit=5):
    """Obtém assets recentes."""
    cursor.execute("""
        SELECT
            title,
            asset_type,
            status,
            file_size_bytes,
            created_at
        FROM assets
        WHERE deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,))
    return cursor.fetchall()


def get_storage_stats(cursor):
    """Obtém estatísticas de storage."""
    cursor.execute("""
        SELECT
            COUNT(*) as locations,
            COUNT(DISTINCT bucket) as buckets,
            SUM(file_size_bytes) as total_size
        FROM asset_storage_locations
    """)
    return cursor.fetchone()


def format_size(size_bytes):
    """Formata tamanho em bytes para formato legível."""
    if size_bytes is None:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_dashboard(asset_stats, job_stats, recent_assets, storage_stats):
    """Imprime o dashboard."""
    clear_screen()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           AKASHI MAM - Database Monitor                      ║")
    print(f"║           Atualizado: {now}                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")

    # Assets
    print(f"{Colors.BOLD}{Colors.GREEN}ASSETS: {asset_stats['total']} total{Colors.ENDC}")
    print(f"   {Colors.GREEN}* available:{Colors.ENDC}  {asset_stats['available']}")
    print(f"   {Colors.YELLOW}* processing:{Colors.ENDC} {asset_stats['processing']}")
    print(f"   {Colors.BLUE}* ingesting:{Colors.ENDC}  {asset_stats['ingesting']}")
    if asset_stats['deleted'] > 0:
        print(f"   {Colors.RED}* deleted:{Colors.ENDC}    {asset_stats['deleted']}")
    print()

    # Jobs
    print(f"{Colors.BOLD}{Colors.BLUE}JOBS: {job_stats['total']} total{Colors.ENDC}")
    print(f"   {Colors.GREEN}* completed:{Colors.ENDC}  {job_stats['completed']}")
    print(f"   {Colors.YELLOW}* pending:{Colors.ENDC}    {job_stats['pending']}")
    print(f"   {Colors.CYAN}* processing:{Colors.ENDC} {job_stats['processing']}")
    if job_stats['failed'] > 0:
        print(f"   {Colors.RED}* failed:{Colors.ENDC}     {job_stats['failed']}")
    print()

    # Storage
    total_size = format_size(storage_stats['total_size'])
    print(f"{Colors.BOLD}{Colors.CYAN}STORAGE:{Colors.ENDC}")
    print(f"   Locations: {storage_stats['locations']} | Buckets: {storage_stats['buckets']} | Total: {total_size}")
    print()

    # Recent Assets
    print(f"{Colors.BOLD}ULTIMOS ASSETS:{Colors.ENDC}")
    print("─" * 64)

    if not recent_assets:
        print("   (nenhum asset encontrado)")
    else:
        for asset in recent_assets:
            title = asset['title'][:30].ljust(30)
            status = asset['status'].ljust(10)
            size = format_size(asset['file_size_bytes']).rjust(10)
            created = asset['created_at'].strftime("%H:%M:%S")

            # Cor do status
            if asset['status'] == 'available':
                status_color = Colors.GREEN
            elif asset['status'] == 'processing':
                status_color = Colors.YELLOW
            elif asset['status'] == 'ingesting':
                status_color = Colors.BLUE
            else:
                status_color = Colors.RED

            print(f"   {title} {status_color}{status}{Colors.ENDC} {size} {created}")

    print("─" * 64)
    print(f"\n{Colors.CYAN}Pressione Ctrl+C para sair{Colors.ENDC}")


def main():
    """Loop principal do monitor."""
    print("Conectando ao banco de dados...")

    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        conn.autocommit = True
        cursor = conn.cursor()

        print("Conectado! Iniciando monitor...")
        time.sleep(1)

        while True:
            try:
                asset_stats = get_asset_stats(cursor)
                job_stats = get_job_stats(cursor)
                recent_assets = get_recent_assets(cursor)
                storage_stats = get_storage_stats(cursor)

                print_dashboard(asset_stats, job_stats, recent_assets, storage_stats)

                time.sleep(2)  # Atualiza a cada 2 segundos

            except psycopg2.OperationalError:
                print("Reconectando ao banco...")
                conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
                conn.autocommit = True
                cursor = conn.cursor()

    except KeyboardInterrupt:
        print("\n\nMonitor encerrado.")
    except Exception as e:
        print(f"Erro: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
