import subprocess
import re
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def run_ytdlp(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip())
    return result.stdout.strip()


def parse_tracks(raw: str) -> list[dict]:
    results = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        vid_id, title, uploader, duration = parts[:4]
        try:
            dur = int(duration)
        except ValueError:
            dur = 0
        results.append({"id": vid_id, "title": title, "uploader": uploader, "duration": dur})
    return results


@app.get("/search")
def search(q: str, limit: int = 20):
    raw = run_ytdlp([
        f"ytsearch{limit}:{q}",
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s",
        "--no-download",
        "--flat-playlist",
    ])
    return parse_tracks(raw)


@app.get("/playlist")
def get_playlist(url: str, limit: int = 200):
    if "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    raw = run_ytdlp([
        url,
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s",
        "--no-download",
        "--flat-playlist",
        "--playlist-end", str(limit),
    ])
    return parse_tracks(raw)


@app.get("/stream")
def stream(id: str):
    if not re.match(r'^[A-Za-z0-9_-]{11}$', id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    raw = run_ytdlp([
        f"https://www.youtube.com/watch?v={id}",
        "--print", "%(url)s\t%(title)s\t%(uploader)s",
        "--format", "bestaudio[ext=m4a]/bestaudio/best",
        "--no-download",
    ])
    parts = raw.split("\t")
    if len(parts) < 3:
        raise HTTPException(status_code=500, detail="Failed to extract stream")
    url, title, uploader = parts[:3]
    return {"url": url, "title": title, "uploader": uploader}


@app.get("/soundcloud/search")
def soundcloud_search(q: str, limit: int = 20):
    raw = run_ytdlp([
        f"scsearch{limit}:{q}",
        "--print", "%(webpage_url)s\t%(title)s\t%(uploader)s\t%(duration)s\t%(thumbnail)s",
        "--no-download",
    ], timeout=120)
    results = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        track_url, title, uploader, duration = parts[:4]
        thumbnail = parts[4] if len(parts) > 4 else ""
        try:
            dur = int(float(duration))
        except (ValueError, TypeError):
            dur = 0
        results.append({
            "id": track_url,
            "title": title,
            "uploader": uploader,
            "duration": dur,
            "thumbnail": thumbnail,
            "source": "soundcloud",
        })
    return results


@app.get("/soundcloud/stream")
def soundcloud_stream(url: str):
    if "soundcloud.com" not in url:
        raise HTTPException(status_code=400, detail="Invalid SoundCloud URL")
    raw = run_ytdlp([
        url,
        "--print", "%(url)s\t%(title)s\t%(uploader)s",
        "--format", "bestaudio/best",
        "--no-download",
    ])
    parts = raw.split("\t")
    if len(parts) < 3:
        raise HTTPException(status_code=500, detail="Failed to extract stream")
    stream_url, title, uploader = parts[:3]
    return {"url": stream_url, "title": title, "uploader": uploader}


@app.get("/proxy")
async def proxy_audio(url: str, request: Request):
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    if "range" in request.headers:
        req_headers["Range"] = request.headers["range"]

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        resp = await client.get(url, headers=req_headers)
        resp_headers = {"Access-Control-Allow-Origin": "*", "Accept-Ranges": "bytes"}
        for h in ("content-length", "content-range"):
            if h in resp.headers:
                resp_headers[h] = resp.headers[h]
        return StreamingResponse(
            resp.aiter_bytes(chunk_size=65536),
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "audio/mp4"),
            headers=resp_headers,
        )
