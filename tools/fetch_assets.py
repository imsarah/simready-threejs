#!/usr/bin/env python3
"""Download SimReady asset folders from the Hugging Face dataset.

Fetches only what the converter needs: the entry .usd stage, payloads/ and
Textures/ (skips source_assets/, .thumbs/ and .metadata/ to save bandwidth).

Usage:
    python fetch_assets.py food_produce_banana_m01 kitchenware_pan_n01
    python fetch_assets.py --list                # show a few available assets

Dataset: https://huggingface.co/datasets/nvidia/simready-assets (CC BY 4.0)
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://huggingface.co/api/datasets/nvidia/simready-assets"
RESOLVE = "https://huggingface.co/datasets/nvidia/simready-assets/resolve/main"


def list_dir(path=""):
    url = f"{API}/tree/main/{path}?recursive=true"
    with urllib.request.urlopen(url) as r:
        return json.load(r)


def wanted(path):
    if ".thumbs" in path or "/source_assets/" in path or ".metadata" in path:
        return False
    return path.endswith((".usd", ".usda", ".usdc", ".png", ".json")) or "/payloads/" in path


def download(job):
    path, size = job
    out = os.path.join("data", path)
    if os.path.exists(out) and size and os.path.getsize(out) == size:
        return path
    os.makedirs(os.path.dirname(out), exist_ok=True)
    url = f"{RESOLVE}/{urllib.parse.quote(path)}"
    with urllib.request.urlopen(url) as r, open(out, "wb") as f:
        f.write(r.read())
    return path


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--list" in sys.argv or not args:
        rows = [e for e in list_dir() if e["type"] == "directory"]
        print(f"{len(rows)} asset folders, e.g.:")
        for e in rows[:40]:
            print("  ", e["path"])
        return
    jobs = []
    for asset in args:
        for e in list_dir(asset):
            if e["type"] == "file" and wanted(e["path"]):
                jobs.append((e["path"], e["size"]))
    print(f"{len(jobs)} files, {sum(s for _, s in jobs) / 1e6:.1f} MB")
    with ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(download, jobs)):
            if i % 10 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)
    print("done -> ./data")


if __name__ == "__main__":
    main()
