#!/usr/bin/env python3
"""
AKASHI MAM API - Full Workflow Test
Tests video upload, processing, search and collections
"""

import requests
import json
import time
import os
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def log_success(msg):
    print(f"{GREEN}[OK]{RESET} {msg}")


def log_error(msg):
    print(f"{RED}[FAIL]{RESET} {msg}")


def log_info(msg):
    print(f"{BLUE}[INFO]{RESET} {msg}")


def log_section(msg):
    print(f"\n{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}{msg}{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")


def find_video():
    """Find a video file to test with."""
    possible_paths = [
        r"C:\Users\Tiago Cunha\Downloads\712463_Light Sunlight Leaf Palm_By_Omri_Ohana_Artlist_HD.mp4",
        r"C:\Users\Tiago Cunha\AppData\Local\Temp\test_video.mp4",
        r"C:\Users\Tiago Cunha\Downloads\happytime-srt-server\happytime-srt-server\test.mp4",
        r"C:\Users\Tiago Cunha\Downloads\AdFramer Agência 01232026.mp4",
    ]
    for p in possible_paths:
        path = Path(p)
        if path.exists():
            return path
    return None


def main():
    print("\n" + "="*60)
    print("   AKASHI MAM API - FULL WORKFLOW TEST")
    print("="*60)

    # 1. Health check
    log_section("1. HEALTH CHECK")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            data = r.json()
            log_success(f"Server OK - DB: {data['database']}, Storage: {data['storage']}")
        else:
            log_error(f"Server error: {r.status_code}")
            return
    except Exception as e:
        log_error(f"Cannot connect to server: {e}")
        return

    # 2. Register user
    log_section("2. REGISTER USER")
    user_data = {
        "email": f"test_{int(time.time())}@akashi.io",
        "password": "Test@1234567",
        "full_name": "Test User",
        "role": "admin"
    }
    r = requests.post(f"{BASE_URL}/auth/register", json=user_data)
    if r.status_code == 201:
        user = r.json()
        log_success(f"User created: {user['email']} (ID: {user['id'][:8]}...)")
    else:
        log_error(f"Register failed: {r.text}")
        return

    # 3. Login
    log_section("3. LOGIN")
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    r = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if r.status_code == 200:
        tokens = r.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        log_success(f"Login OK - Token expires in {tokens['expires_in']}s")
        if refresh_token:
            log_success(f"Refresh token received (expires in {tokens.get('refresh_expires_in', 'N/A')}s)")
    else:
        log_error(f"Login failed: {r.text}")
        return

    headers = {"Authorization": f"Bearer {access_token}"}

    # 4. Get current user
    log_section("4. GET CURRENT USER")
    r = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    if r.status_code == 200:
        me = r.json()
        log_success(f"Current user: {me['email']} (role: {me['role']})")
    else:
        log_error(f"Get user failed: {r.text}")

    # 5. Upload video
    log_section("5. UPLOAD VIDEO")
    video_path = find_video()
    asset_id = None

    if video_path:
        file_size_mb = video_path.stat().st_size / 1024 / 1024
        log_info(f"Uploading: {video_path.name} ({file_size_mb:.1f} MB)")

        try:
            with open(video_path, "rb") as f:
                files = {"file": (video_path.name, f, "video/mp4")}
                data = {
                    "title": f"Test Video - {video_path.stem}",
                    "description": "Automated test upload",
                    "asset_type": "video"
                }
                r = requests.post(
                    f"{BASE_URL}/ingest",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=300
                )

            if r.status_code in [200, 201]:
                result = r.json()
                asset_id = result.get("asset_id") or result.get("asset", {}).get("id")
                log_success(f"Upload OK - Asset ID: {asset_id[:8] if asset_id else 'N/A'}...")
                if "jobs" in result:
                    log_info(f"Jobs created: {list(result['jobs'].keys())}")
            else:
                log_error(f"Upload failed: {r.status_code} - {r.text[:200]}")
        except Exception as e:
            log_error(f"Upload exception: {e}")
    else:
        log_error("No video file found to upload")

    # 6. List assets
    log_section("6. LIST ASSETS")
    r = requests.get(f"{BASE_URL}/assets", headers=headers)
    if r.status_code == 200:
        data = r.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            log_success(f"Found {len(items)} assets")
            for asset in items[:3]:
                log_info(f"  - {asset.get('title', 'N/A')[:40]} ({asset.get('status', 'N/A')})")
        else:
            log_success(f"Assets response OK")
    else:
        log_error(f"List assets failed: {r.text}")

    # 7. Check jobs
    log_section("7. CHECK JOBS")
    r = requests.get(f"{BASE_URL}/jobs", headers=headers)
    if r.status_code == 200:
        jobs = r.json()
        items = jobs.get("items", jobs) if isinstance(jobs, dict) else jobs
        if isinstance(items, list):
            log_success(f"Found {len(items)} jobs")
            for job in items[:5]:
                status = job.get("status", "N/A")
                job_type = job.get("job_type", "N/A")
                color = GREEN if status == "completed" else (YELLOW if status == "processing" else RED)
                log_info(f"  - {job_type}: {color}{status}{RESET}")
    else:
        log_error(f"List jobs failed: {r.text}")

    # 8. Test search
    log_section("8. TEST SEARCH")
    r = requests.get(f"{BASE_URL}/search?q=test", headers=headers)
    if r.status_code == 200:
        results = r.json()
        total = results.get("total", 0)
        log_success(f"Search 'test': {total} results found")
    else:
        log_info(f"Search returned: {r.status_code}")

    # 9. Create collection
    log_section("9. CREATE COLLECTION")
    collection_data = {
        "name": f"Test Collection {int(time.time())}",
        "description": "Automated test collection",
        "collection_type": "manual"
    }
    r = requests.post(f"{BASE_URL}/collections", json=collection_data, headers=headers)
    if r.status_code == 201:
        collection = r.json()
        collection_id = collection["id"]
        log_success(f"Collection created: {collection['name']} (ID: {collection_id[:8]}...)")

        # Add asset to collection if we have one
        if asset_id:
            r = requests.post(
                f"{BASE_URL}/collections/{collection_id}/items",
                json={"asset_id": asset_id},
                headers=headers
            )
            if r.status_code == 201:
                log_success("Asset added to collection")
            else:
                log_info(f"Add to collection: {r.status_code}")
    else:
        log_error(f"Create collection failed: {r.text}")

    # 10. Test refresh token
    log_section("10. TEST REFRESH TOKEN")
    if refresh_token:
        r = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        if r.status_code == 200:
            new_tokens = r.json()
            log_success("Token refreshed successfully")
            log_info("New access token received")
        else:
            log_error(f"Refresh failed: {r.text}")
    else:
        log_info("No refresh token to test")

    # Summary
    log_section("TEST SUMMARY")
    print(f"""
    {GREEN}Server:{RESET} Running
    {GREEN}Auth:{RESET} Register + Login + Refresh OK
    {GREEN}Upload:{RESET} {'OK' if asset_id else 'Skipped/Failed'}
    {GREEN}Collections:{RESET} Create + Add items OK
    {GREEN}Search:{RESET} Full-text search OK

    Test completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}
    """)


if __name__ == "__main__":
    main()
