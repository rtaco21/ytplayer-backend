import subprocess
import json
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def run_ytdlp(args: list[str]) -> dict:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip())
    return result.stdout.strip()


@app.get("/search")
def search(q: str, limit: int = 10):
    raw = run_ytdlp([
        f"ytsearch{limit}:{q}",
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s\t%(thumbnail)s",
        "--no-download",
        "--flat-playlist",
    ])
    results = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        vid_id, title, uploader, duration, thumbnail = parts[:5]
        try:
            dur = int(duration)
        except ValueError:
            dur = 0
        results.append({
            "id": vid_id,
            "title": title,
            "uploader": uploader,
            "duration": dur,
            "thumbnail": thumbnail,
        })
    return results


@app.get("/stream")
def stream(id: str):
    if not re.match(r'^[A-Za-z0-9_-]{11}$', id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    raw = run_ytdlp([
        f"https://www.youtube.com/watch?v={id}",
        "--print", "%(url)s\t%(title)s\t%(uploader)s\t%(thumbnail)s",
        "--format", "bestaudio[ext=m4a]/bestaudio/best",
        "--no-download",
    ])
    parts = raw.split("\t")
    if len(parts) < 4:
        raise HTTPException(status_code=500, detail="Failed to extract stream")
    url, title, uploader, thumbnail = parts[:4]
    return {"url": url, "title": title, "uploader": uploader, "thumbnail": thumbnail}
