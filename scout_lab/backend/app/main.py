from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "output"
CLIPS_DIR = ROOT / "clips_input"
DATA_DIR = ROOT / "scout_lab" / "data"
DB_PATH = DATA_DIR / "scout_lab.db"

RADAR_SCRIPT = ROOT / "vista_tattica" / "genera_radar_auto.py"
STATS_SCRIPT = ROOT / "analisi" / "stats_giocatori.py"
METRICS_SCRIPT = ROOT / "analisi" / "metriche_avanzate.py"
REPORT_SCRIPT = ROOT / "analisi" / "report_pdf.py"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)


def _load_secrets() -> None:
    """Carica le chiavi (es. RUNPOD_API_KEY) da scout_lab/data/secrets.env (ignorato da git)."""
    env_file = DATA_DIR / "secrets.env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_secrets()

app = FastAPI(title="Scout Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict[str, Any]] = {}


class AnnotationUpdate(BaseModel):
    player_name: str | None = None
    jersey_number: str | None = None
    role: str | None = None
    team_override: int | None = None
    notes: str | None = None


class InsightRequest(BaseModel):
    analysis_id: int
    track_db_id: int | None = None
    profile_id: int | None = None
    model: str
    api_key: str | None = None
    extra_context: str | None = None


class LocalRunRequest(BaseModel):
    filename: str
    salto: int = 3
    ogni_campo: int = 2
    no_video: bool = True
    use_runpod: bool = False   # esegue il passo GPU su un pod RunPod invece che in locale


class ProfileUpsert(BaseModel):
    analysis_id: int
    track_db_ids: list[int]
    display_name: str = ""
    jersey_number: str = ""
    role: str = ""
    team: int | None = None
    notes: str = ""


class ProfileTrackLink(BaseModel):
    track_db_id: int
    propagate_identity: bool = True


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            create table if not exists analyses (
                id integer primary key autoincrement,
                base text unique not null,
                title text not null,
                created_at text not null,
                positions_csv text not null,
                stats_csv text,
                dashboard_png text,
                radar_mp4 text,
                source_video text,
                report_pdf text,
                duration_s real default 0,
                frame_count integer default 0,
                track_count integer default 0,
                quality_score integer default 0,
                quality_label text default 'Da valutare',
                quality_notes text default ''
            );

            create table if not exists tracks (
                id integer primary key autoincrement,
                analysis_id integer not null,
                track_id integer not null,
                team integer default 0,
                n_points integer default 0,
                duration_s real default 0,
                first_time_s real default 0,
                last_time_s real default 0,
                start_x real default 0,
                start_y real default 0,
                end_x real default 0,
                end_y real default 0,
                x_avg real default 0,
                y_avg real default 0,
                area_m2 real default 0,
                distance_m real default 0,
                vmax_kmh real default 0,
                zone text default '',
                confidence integer default 0,
                player_name text default '',
                jersey_number text default '',
                role text default '',
                team_override integer,
                notes text default '',
                unique(analysis_id, track_id)
            );

            create table if not exists ai_reports (
                id integer primary key autoincrement,
                analysis_id integer not null,
                track_db_id integer,
                profile_id integer,
                model text not null,
                prompt text not null,
                content text not null,
                created_at text not null
            );

            create table if not exists player_profiles (
                id integer primary key autoincrement,
                analysis_id integer not null,
                display_name text default '',
                jersey_number text default '',
                role text default '',
                team integer,
                notes text default '',
                created_at text not null
            );

            create table if not exists profile_tracks (
                profile_id integer not null,
                track_db_id integer not null,
                primary key (profile_id, track_db_id)
            );
            """
        )
        cols = {r["name"] for r in conn.execute("pragma table_info(ai_reports)").fetchall()}
        if "profile_id" not in cols:
            conn.execute("alter table ai_reports add column profile_id integer")
        analysis_cols = {r["name"] for r in conn.execute("pragma table_info(analyses)").fetchall()}
        if "source_video" not in analysis_cols:
            conn.execute("alter table analyses add column source_video text")
        track_cols = {r["name"] for r in conn.execute("pragma table_info(tracks)").fetchall()}
        for name in ("start_x", "start_y", "end_x", "end_y"):
            if name not in track_cols:
                conn.execute(f"alter table tracks add column {name} real default 0")


def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def zone_from_xy(x: float, y: float) -> str:
    lane = "sinistra" if y < 23 else ("destra" if y > 45 else "centrale")
    depth = "bassa" if x < 35 else ("alta" if x > 70 else "media")
    return f"{lane} {depth}"


def aggregate_tracks(rows: list[dict[str, str]], stats_rows: list[dict[str, str]]) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    by_track: dict[int, list[dict[str, str]]] = defaultdict(list)
    ball_rows = 0
    times: list[float] = []
    frame_values: set[str] = set()

    for row in rows:
        pid = int(safe_float(row.get("id_giocatore")))
        times.append(safe_float(row.get("tempo_s")))
        frame_values.add(str(row.get("frame", "")))
        if pid == 0:
            ball_rows += 1
            continue
        by_track[pid].append(row)

    stats_by_id = {int(safe_float(r.get("id_giocatore"))): r for r in stats_rows}
    tracks: dict[int, dict[str, Any]] = {}

    for pid, pts in by_track.items():
        pts_sorted = sorted(pts, key=lambda r: safe_float(r.get("tempo_s")))
        xs = [safe_float(p.get("x_m")) for p in pts_sorted]
        ys = [safe_float(p.get("y_m")) for p in pts_sorted]
        ts = [safe_float(p.get("tempo_s")) for p in pts_sorted]
        teams = [int(safe_float(p.get("squadra"))) for p in pts_sorted]

        distance = 0.0
        vmax = 0.0
        for prev, cur in zip(range(len(pts_sorted) - 1), range(1, len(pts_sorted))):
            dt = ts[cur] - ts[prev]
            if dt <= 0:
                continue
            d = ((xs[cur] - xs[prev]) ** 2 + (ys[cur] - ys[prev]) ** 2) ** 0.5
            v = d / dt
            if v <= 10:
                distance += d
                vmax = max(vmax, v * 3.6)

        stat = stats_by_id.get(pid, {})
        n = len(pts_sorted)
        duration = max(ts) - min(ts) if ts else 0
        x_avg = sum(xs) / max(1, len(xs))
        y_avg = sum(ys) / max(1, len(ys))
        x_span = max(xs) - min(xs) if xs else 0
        y_span = max(ys) - min(ys) if ys else 0
        confidence = min(95, int(25 + min(n, 160) * 0.35 + min(duration, 90) * 0.25))

        tracks[pid] = {
            "track_id": pid,
            "team": Counter(teams).most_common(1)[0][0] if teams else 0,
            "n_points": n,
            "duration_s": round(duration, 2),
            "first_time_s": min(ts) if ts else 0,
            "last_time_s": max(ts) if ts else 0,
            "start_x": round(xs[0], 2) if xs else 0,
            "start_y": round(ys[0], 2) if ys else 0,
            "end_x": round(xs[-1], 2) if xs else 0,
            "end_y": round(ys[-1], 2) if ys else 0,
            "x_avg": round(safe_float(stat.get("x_medio"), x_avg), 2),
            "y_avg": round(safe_float(stat.get("y_medio"), y_avg), 2),
            "area_m2": round(safe_float(stat.get("area_azione_m2"), x_span * y_span), 1),
            "distance_m": round(safe_float(stat.get("distanza_m_approx"), distance), 1),
            "vmax_kmh": round(safe_float(stat.get("vel_max_kmh_approx"), vmax), 1),
            "zone": stat.get("zona") or zone_from_xy(x_avg, y_avg),
            "confidence": confidence,
        }

    duration = max(times) - min(times) if times else 0
    avg_track_duration = sum(t["duration_s"] for t in tracks.values()) / max(1, len(tracks))
    long_tracks = sum(1 for t in tracks.values() if t["duration_s"] >= 20)
    quality = int(min(95, 25 + min(duration, 120) * 0.2 + min(long_tracks, 22) * 1.8 + (10 if ball_rows else 0)))
    if quality >= 75:
        label = "Buona per profilo clip"
    elif quality >= 55:
        label = "Usabile con revisione"
    else:
        label = "Debole: serve revisione forte"
    notes = (
        f"Durata {duration:.1f}s, {len(tracks)} tracce, "
        f"durata media tracce {avg_track_duration:.1f}s, palla rilevata {ball_rows} volte."
    )
    summary = {
        "duration_s": round(duration, 2),
        "frame_count": len(frame_values),
        "track_count": len(tracks),
        "quality_score": quality,
        "quality_label": label,
        "quality_notes": notes,
    }
    return tracks, summary


def find_source_video(base: str) -> str | None:
    for suffix in (".mp4", ".mov", ".mkv", ".avi", ".webm"):
        candidate = CLIPS_DIR / f"{base}{suffix}"
        if candidate.exists():
            return str(candidate)
    return None


def video_codec(path: Path) -> str:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=nk=1:nw=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.stdout.strip().lower()
    except Exception:
        return ""


def web_compatible_video(path: Path, stem: str) -> str | None:
    if not path.exists():
        return None
    codec = video_codec(path)
    if not codec:
        return None
    if codec in {"h264", "avc1"}:
        return str(path)
    web_path = OUTPUT_DIR / f"{stem}_WEB.mp4"
    if web_path.exists() and web_path.stat().st_mtime >= path.stat().st_mtime:
        return str(web_path)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(web_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if proc.returncode != 0 or not web_path.exists():
        return None
    return str(web_path)


def output_files_for_base(base: str) -> dict[str, str | None]:
    radar_path = OUTPUT_DIR / f"RADARAUTO_{base}.mp4"
    return {
        "positions_csv": str(OUTPUT_DIR / f"POSIZIONIAUTO_{base}.csv"),
        "stats_csv": str(OUTPUT_DIR / f"STATISTICHE_{base}.csv") if (OUTPUT_DIR / f"STATISTICHE_{base}.csv").exists() else None,
        "dashboard_png": str(OUTPUT_DIR / f"DASHBOARD_{base}.png") if (OUTPUT_DIR / f"DASHBOARD_{base}.png").exists() else None,
        "radar_mp4": web_compatible_video(radar_path, f"RADARAUTO_{base}") if radar_path.exists() else None,
        "source_video": find_source_video(base),
        "report_pdf": str(OUTPUT_DIR / f"REPORT_COMPLETO_{base}.pdf") if (OUTPUT_DIR / f"REPORT_COMPLETO_{base}.pdf").exists() else None,
    }


def report_bundle(base: str) -> dict[str, Any]:
    """Assets del report tattico (immagini + metriche squadra) per la pagina Risultati."""
    def img(name: str) -> str | None:
        p = OUTPUT_DIR / name
        return media_url(str(p)) if p.exists() else None

    team_rows = read_rows(OUTPUT_DIR / f"METRICHE_SQUADRE_{base}.csv")
    heat_dir = OUTPUT_DIR / f"heatmaps_{base}"
    return {
        "formazione": img(f"FORMAZIONE_{base}.png"),
        "andamento": img(f"ANDAMENTO_{base}.png"),
        "dashboard": img(f"DASHBOARD_{base}.png"),
        "report_png": img(f"REPORT_{base}.png"),
        "report_pdf": media_url(str(OUTPUT_DIR / f"REPORT_COMPLETO_{base}.pdf")) if (OUTPUT_DIR / f"REPORT_COMPLETO_{base}.pdf").exists() else None,
        "heatmap_team1": media_url(str(heat_dir / "_SQUADRA_1.png")) if (heat_dir / "_SQUADRA_1.png").exists() else None,
        "heatmap_team2": media_url(str(heat_dir / "_SQUADRA_2.png")) if (heat_dir / "_SQUADRA_2.png").exists() else None,
        "team_metrics": team_rows,
    }


def sync_outputs() -> dict[str, int]:
    init_db()
    imported = 0
    updated = 0
    with db() as conn:
        for csv_path in sorted(OUTPUT_DIR.glob("POSIZIONIAUTO_*.csv")):
            base = csv_path.stem.replace("POSIZIONIAUTO_", "")
            files = output_files_for_base(base)
            rows = read_rows(csv_path)
            stats_rows = read_rows(Path(files["stats_csv"])) if files["stats_csv"] else []
            tracks, summary = aggregate_tracks(rows, stats_rows)
            exists = conn.execute("select id from analyses where base = ?", (base,)).fetchone()
            if exists:
                analysis_id = int(exists["id"])
                updated += 1
                conn.execute(
                    """
                    update analyses set positions_csv=?, stats_csv=?, dashboard_png=?, radar_mp4=?, source_video=?, report_pdf=?,
                    duration_s=?, frame_count=?, track_count=?, quality_score=?, quality_label=?, quality_notes=?
                    where id=?
                    """,
                    (
                        files["positions_csv"],
                        files["stats_csv"],
                        files["dashboard_png"],
                        files["radar_mp4"],
                        files["source_video"],
                        files["report_pdf"],
                        summary["duration_s"],
                        summary["frame_count"],
                        summary["track_count"],
                        summary["quality_score"],
                        summary["quality_label"],
                        summary["quality_notes"],
                        analysis_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    insert into analyses (
                        base, title, created_at, positions_csv, stats_csv, dashboard_png, radar_mp4, source_video, report_pdf,
                        duration_s, frame_count, track_count, quality_score, quality_label, quality_notes
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        base,
                        base.replace("_", " "),
                        now_iso(),
                        files["positions_csv"],
                        files["stats_csv"],
                        files["dashboard_png"],
                        files["radar_mp4"],
                        files["source_video"],
                        files["report_pdf"],
                        summary["duration_s"],
                        summary["frame_count"],
                        summary["track_count"],
                        summary["quality_score"],
                        summary["quality_label"],
                        summary["quality_notes"],
                    ),
                )
                analysis_id = int(cur.lastrowid)
                imported += 1

            for track in tracks.values():
                old = conn.execute(
                    "select player_name, jersey_number, role, team_override, notes from tracks where analysis_id=? and track_id=?",
                    (analysis_id, track["track_id"]),
                ).fetchone()
                annotation = dict(old) if old else {}
                conn.execute(
                    """
                    insert into tracks (
                        analysis_id, track_id, team, n_points, duration_s, first_time_s, last_time_s,
                        start_x, start_y, end_x, end_y, x_avg, y_avg, area_m2, distance_m, vmax_kmh, zone, confidence,
                        player_name, jersey_number, role, team_override, notes
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(analysis_id, track_id) do update set
                        team=excluded.team, n_points=excluded.n_points, duration_s=excluded.duration_s,
                        first_time_s=excluded.first_time_s, last_time_s=excluded.last_time_s,
                        start_x=excluded.start_x, start_y=excluded.start_y, end_x=excluded.end_x, end_y=excluded.end_y,
                        x_avg=excluded.x_avg, y_avg=excluded.y_avg, area_m2=excluded.area_m2,
                        distance_m=excluded.distance_m, vmax_kmh=excluded.vmax_kmh,
                        zone=excluded.zone, confidence=excluded.confidence
                    """,
                    (
                        analysis_id,
                        track["track_id"],
                        track["team"],
                        track["n_points"],
                        track["duration_s"],
                        track["first_time_s"],
                        track["last_time_s"],
                        track["start_x"],
                        track["start_y"],
                        track["end_x"],
                        track["end_y"],
                        track["x_avg"],
                        track["y_avg"],
                        track["area_m2"],
                        track["distance_m"],
                        track["vmax_kmh"],
                        track["zone"],
                        track["confidence"],
                        annotation.get("player_name", ""),
                        annotation.get("jersey_number", ""),
                        annotation.get("role", ""),
                        annotation.get("team_override"),
                        annotation.get("notes", ""),
                    ),
                )
    return {"imported": imported, "updated": updated}


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/api/v1/media?path={urllib.parse.quote(path)}"


def analysis_payload(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["assets"] = {
        "dashboard": media_url(item.get("dashboard_png")),
        "radar": media_url(item.get("radar_mp4")),
        "clip": media_url(item.get("source_video")),
        "report": media_url(item.get("report_pdf")),
    }
    return item


@app.on_event("startup")
def startup() -> None:
    sync_outputs()


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return {"ok": True, "root": str(ROOT), "db": str(DB_PATH)}


@app.post("/api/v1/sync")
def sync() -> dict[str, int]:
    return sync_outputs()


@app.get("/api/v1/analyses")
def analyses() -> list[dict[str, Any]]:
    sync_outputs()
    with db() as conn:
        rows = conn.execute("select * from analyses order by created_at desc, id desc").fetchall()
    return [analysis_payload(r) for r in rows]


@app.get("/api/v1/analyses/{analysis_id}")
def analysis_detail(analysis_id: int) -> dict[str, Any]:
    with db() as conn:
        analysis = conn.execute("select * from analyses where id=?", (analysis_id,)).fetchone()
        if not analysis:
            raise HTTPException(404, "Analisi non trovata")
        tracks = conn.execute(
            "select * from tracks where analysis_id=? order by n_points desc limit 300", (analysis_id,)
        ).fetchall()
        reports = conn.execute(
            "select * from ai_reports where analysis_id=? order by id desc limit 20", (analysis_id,)
        ).fetchall()
        profiles = conn.execute(
            """
            select p.*,
                   count(pt.track_db_id) as track_count,
                   coalesce(sum(t.n_points), 0) as n_points,
                   coalesce(sum(t.duration_s), 0) as observed_s,
                   coalesce(avg(t.confidence), 0) as avg_confidence
            from player_profiles p
            left join profile_tracks pt on pt.profile_id = p.id
            left join tracks t on t.id = pt.track_db_id
            where p.analysis_id=?
            group by p.id
            order by p.id desc
            """,
            (analysis_id,),
        ).fetchall()
    payload = analysis_payload(analysis)
    payload["tracks"] = [dict(t) for t in tracks]
    payload["reports"] = [dict(r) for r in reports]
    payload["profiles"] = [dict(p) for p in profiles]
    payload["report"] = report_bundle(analysis["base"])
    return payload


def merge_score(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    team_a = a.get("team_override") or a.get("team")
    team_b = b.get("team_override") or b.get("team")
    if team_a and team_b and team_a != team_b:
        return None
    if a["last_time_s"] <= b["first_time_s"]:
        first, second = a, b
        gap = b["first_time_s"] - a["last_time_s"]
        dist = ((a["end_x"] - b["start_x"]) ** 2 + (a["end_y"] - b["start_y"]) ** 2) ** 0.5
    elif b["last_time_s"] <= a["first_time_s"]:
        first, second = b, a
        gap = a["first_time_s"] - b["last_time_s"]
        dist = ((b["end_x"] - a["start_x"]) ** 2 + (b["end_y"] - a["start_y"]) ** 2) ** 0.5
    else:
        overlap = min(a["last_time_s"], b["last_time_s"]) - max(a["first_time_s"], b["first_time_s"])
        if overlap > 2.0:
            return None
        first, second = (a, b) if a["first_time_s"] <= b["first_time_s"] else (b, a)
        gap = 0.0
        dist = ((a["x_avg"] - b["x_avg"]) ** 2 + (a["y_avg"] - b["y_avg"]) ** 2) ** 0.5
    if gap > 12 or dist > 28:
        return None
    zone_bonus = 8 if a.get("zone") == b.get("zone") else 0
    conf_bonus = min(a.get("confidence", 0), b.get("confidence", 0)) * 0.12
    score = int(max(0, min(98, 92 - gap * 4.2 - dist * 1.7 + zone_bonus + conf_bonus)))
    if score < 38:
        return None
    return {
        "score": score,
        "gap_s": round(gap, 2),
        "distance_m": round(dist, 2),
        "track_ids": [a["id"], b["id"]],
        "track_labels": [f"#{a['track_id']}", f"#{b['track_id']}"],
        "ordered_track_ids": [first["id"], second["id"]],
        "reason": f"gap {gap:.1f}s, distanza {dist:.1f}m, squadra {team_a or team_b or 'n/d'}",
        "tracks": [a, b],
    }


@app.get("/api/v1/analyses/{analysis_id}/merge-suggestions")
def merge_suggestions(analysis_id: int, limit: int = 24) -> list[dict[str, Any]]:
    with db() as conn:
        used = {
            r["track_db_id"]
            for r in conn.execute(
                """
                select pt.track_db_id from profile_tracks pt
                join player_profiles p on p.id = pt.profile_id
                where p.analysis_id=?
                """,
                (analysis_id,),
            ).fetchall()
        }
        rows = conn.execute(
            """
            select * from tracks
            where analysis_id=? and n_points >= 12
            order by first_time_s, n_points desc
            limit 260
            """,
            (analysis_id,),
        ).fetchall()
    tracks = [dict(r) for r in rows if r["id"] not in used]
    suggestions: list[dict[str, Any]] = []
    for i, a in enumerate(tracks):
        for b in tracks[i + 1 :]:
            if abs(a["first_time_s"] - b["first_time_s"]) > 45 and abs(a["last_time_s"] - b["first_time_s"]) > 18:
                continue
            item = merge_score(a, b)
            if item:
                suggestions.append(item)
    suggestions.sort(key=lambda s: (-s["score"], s["gap_s"], s["distance_m"]))
    return suggestions[: max(1, min(limit, 60))]


def identity_score(profile: dict[str, Any], profile_tracks: list[dict[str, Any]], track: dict[str, Any]) -> dict[str, Any] | None:
    profile_team = profile.get("team")
    track_team = track.get("team_override") or track.get("team")
    if profile_team and track_team and profile_team != track_team:
        return None
    if not profile_tracks:
        return None

    nearest: dict[str, Any] | None = None
    for anchor in profile_tracks:
        if anchor["id"] == track["id"]:
            return None
        item = merge_score(anchor, track)
        if not item:
            continue
        if nearest is None or item["score"] > nearest["score"]:
            nearest = item
    if not nearest:
        return None

    name_bonus = 4 if profile.get("display_name") else 0
    number_bonus = 5 if profile.get("jersey_number") else 0
    role_bonus = 3 if profile.get("role") and track.get("zone") else 0
    duration_bonus = min(8, float(track.get("duration_s") or 0) * 0.6)
    score = int(min(99, nearest["score"] + name_bonus + number_bonus + role_bonus + duration_bonus))
    if score < 45:
        return None
    if score >= 82:
        status = "alta"
    elif score >= 65:
        status = "media"
    else:
        status = "bassa"
    return {
        "score": score,
        "status": status,
        "profile": profile,
        "track": track,
        "anchor_track": nearest["tracks"][0] if nearest["tracks"][0]["id"] != track["id"] else nearest["tracks"][1],
        "reason": f"{nearest['reason']}, identita {status}",
    }


@app.get("/api/v1/analyses/{analysis_id}/identity-suggestions")
def identity_suggestions(analysis_id: int, limit: int = 24) -> dict[str, Any]:
    with db() as conn:
        profiles = [dict(r) for r in conn.execute("select * from player_profiles where analysis_id=? order by id desc", (analysis_id,)).fetchall()]
        profile_tracks: dict[int, list[dict[str, Any]]] = {}
        used: set[int] = set()
        for profile in profiles:
            rows = conn.execute(
                """
                select t.* from tracks t
                join profile_tracks pt on pt.track_db_id = t.id
                where pt.profile_id=?
                order by t.first_time_s
                """,
                (profile["id"],),
            ).fetchall()
            items = [dict(r) for r in rows]
            profile_tracks[profile["id"]] = items
            used.update(t["id"] for t in items)
        rows = conn.execute(
            """
            select * from tracks
            where analysis_id=? and n_points >= 12 and duration_s >= 3 and confidence >= 25
            order by duration_s desc, confidence desc
            limit 320
            """,
            (analysis_id,),
        ).fetchall()

    candidates = [dict(r) for r in rows if r["id"] not in used]
    suggestions: list[dict[str, Any]] = []
    for track in candidates:
        best = None
        for profile in profiles:
            item = identity_score(profile, profile_tracks.get(profile["id"], []), track)
            if item and (best is None or item["score"] > best["score"]):
                best = item
        if best:
            suggestions.append(best)
    suggestions.sort(key=lambda s: (-s["score"], s["track"]["first_time_s"]))
    return {
        "profiles": len(profiles),
        "unassigned_tracks": len(candidates),
        "suggestions": suggestions[: max(1, min(limit, 80))],
        "note": "Suggerimenti euristici: confermare su clip/radar prima di applicare.",
    }


@app.patch("/api/v1/tracks/{track_db_id}")
def update_track(track_db_id: int, data: AnnotationUpdate) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("select * from tracks where id=?", (track_db_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Traccia non trovata")
        conn.execute(
            """
            update tracks set player_name=?, jersey_number=?, role=?, team_override=?, notes=? where id=?
            """,
            (
                data.player_name or "",
                data.jersey_number or "",
                data.role or "",
                data.team_override,
                data.notes or "",
                track_db_id,
            ),
        )
        updated = conn.execute("select * from tracks where id=?", (track_db_id,)).fetchone()
    return dict(updated)


def aggregate_profile_rows(rows: list[sqlite3.Row]) -> dict[str, Any]:
    tracks = [dict(r) for r in rows]
    if not tracks:
        return {
            "track_count": 0,
            "n_points": 0,
            "observed_s": 0,
            "x_avg": 0,
            "y_avg": 0,
            "area_m2": 0,
            "distance_m": 0,
            "vmax_kmh": 0,
            "confidence": 0,
            "first_time_s": 0,
            "last_time_s": 0,
        }
    n_points = sum(t["n_points"] for t in tracks)
    weight = max(1, n_points)
    return {
        "track_count": len(tracks),
        "n_points": n_points,
        "observed_s": round(sum(t["duration_s"] for t in tracks), 2),
        "x_avg": round(sum(t["x_avg"] * t["n_points"] for t in tracks) / weight, 2),
        "y_avg": round(sum(t["y_avg"] * t["n_points"] for t in tracks) / weight, 2),
        "area_m2": round(sum(t["area_m2"] for t in tracks), 1),
        "distance_m": round(sum(t["distance_m"] for t in tracks), 1),
        "vmax_kmh": round(max(t["vmax_kmh"] for t in tracks), 1),
        "confidence": round(sum(t["confidence"] * t["n_points"] for t in tracks) / weight),
        "first_time_s": round(min(t["first_time_s"] for t in tracks), 2),
        "last_time_s": round(max(t["last_time_s"] for t in tracks), 2),
    }


@app.post("/api/v1/profiles")
def create_profile(data: ProfileUpsert) -> dict[str, Any]:
    if not data.track_db_ids:
        raise HTTPException(400, "Seleziona almeno una traccia")
    with db() as conn:
        q = ",".join("?" for _ in data.track_db_ids)
        tracks = conn.execute(
            f"select * from tracks where analysis_id=? and id in ({q})",
            (data.analysis_id, *data.track_db_ids),
        ).fetchall()
        if len(tracks) != len(set(data.track_db_ids)):
            raise HTTPException(400, "Una o piu tracce non appartengono all'analisi")
        inferred_team = data.team
        if inferred_team is None and tracks:
            teams = [dict(t).get("team_override") or dict(t).get("team") for t in tracks]
            inferred_team = Counter(teams).most_common(1)[0][0]
        cur = conn.execute(
            """
            insert into player_profiles (analysis_id, display_name, jersey_number, role, team, notes, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.analysis_id,
                data.display_name,
                data.jersey_number,
                data.role,
                inferred_team,
                data.notes,
                now_iso(),
            ),
        )
        profile_id = int(cur.lastrowid)
        for track_id in data.track_db_ids:
            conn.execute(
                "insert or ignore into profile_tracks (profile_id, track_db_id) values (?, ?)",
                (profile_id, track_id),
            )
        rows = conn.execute(
            "select * from tracks where id in (" + q + ")",
            tuple(data.track_db_ids),
        ).fetchall()
    return {"id": profile_id, **data.model_dump(), "team": inferred_team, "aggregate": aggregate_profile_rows(rows)}


@app.get("/api/v1/profiles/{profile_id}")
def profile_detail(profile_id: int) -> dict[str, Any]:
    with db() as conn:
        profile = conn.execute("select * from player_profiles where id=?", (profile_id,)).fetchone()
        if not profile:
            raise HTTPException(404, "Profilo non trovato")
        tracks = conn.execute(
            """
            select t.* from tracks t
            join profile_tracks pt on pt.track_db_id = t.id
            where pt.profile_id=?
            order by t.first_time_s
            """,
            (profile_id,),
        ).fetchall()
    return {"profile": dict(profile), "tracks": [dict(t) for t in tracks], "aggregate": aggregate_profile_rows(tracks)}


@app.post("/api/v1/profiles/{profile_id}/tracks")
def add_track_to_profile(profile_id: int, data: ProfileTrackLink) -> dict[str, Any]:
    with db() as conn:
        profile = conn.execute("select * from player_profiles where id=?", (profile_id,)).fetchone()
        if not profile:
            raise HTTPException(404, "Profilo non trovato")
        track = conn.execute("select * from tracks where id=? and analysis_id=?", (data.track_db_id, profile["analysis_id"])).fetchone()
        if not track:
            raise HTTPException(404, "Track ID non trovato per questa analisi")
        existing = conn.execute(
            """
            select p.id, p.display_name from profile_tracks pt
            join player_profiles p on p.id = pt.profile_id
            where pt.track_db_id=?
            """,
            (data.track_db_id,),
        ).fetchone()
        if existing and existing["id"] != profile_id:
            raise HTTPException(409, f"Track ID gia assegnato a {existing['display_name'] or 'un altro profilo'}")
        conn.execute(
            "insert or ignore into profile_tracks (profile_id, track_db_id) values (?, ?)",
            (profile_id, data.track_db_id),
        )
        if data.propagate_identity:
            conn.execute(
                """
                update tracks
                set player_name=coalesce(nullif(?, ''), player_name),
                    jersey_number=coalesce(nullif(?, ''), jersey_number),
                    role=coalesce(nullif(?, ''), role),
                    team_override=coalesce(?, team_override)
                where id=?
                """,
                (
                    profile["display_name"] or "",
                    profile["jersey_number"] or "",
                    profile["role"] or "",
                    profile["team"],
                    data.track_db_id,
                ),
            )
        rows = conn.execute(
            """
            select t.* from tracks t
            join profile_tracks pt on pt.track_db_id = t.id
            where pt.profile_id=?
            order by t.first_time_s
            """,
            (profile_id,),
        ).fetchall()
    return {"profile": dict(profile), "tracks": [dict(t) for t in rows], "aggregate": aggregate_profile_rows(rows)}


@app.get("/api/v1/profiles/{profile_id}/export.md")
def export_profile_markdown(profile_id: int) -> FileResponse:
    detail = profile_detail(profile_id)
    p = detail["profile"]
    agg = detail["aggregate"]
    tracks = detail["tracks"]
    name = p.get("display_name") or f"Profilo {profile_id}"
    content = [
        f"# {name}",
        "",
        f"- Numero: {p.get('jersey_number') or 'n/d'}",
        f"- Ruolo: {p.get('role') or 'n/d'}",
        f"- Squadra: {p.get('team') or 'n/d'}",
        f"- Tracce unite: {agg['track_count']}",
        f"- Durata osservata aggregata: {agg['observed_s']}s",
        f"- Posizione media: x={agg['x_avg']}, y={agg['y_avg']}",
        f"- Distanza indicativa: {agg['distance_m']}m",
        f"- Vmax indicativa: {agg['vmax_kmh']}km/h",
        f"- Confidenza aggregata: {agg['confidence']}/100",
        "",
        "## Note",
        p.get("notes") or "-",
        "",
        "## Track ID",
        ", ".join(f"#{t['track_id']}" for t in tracks) or "-",
    ]
    path = DATA_DIR / f"profile_{profile_id}.md"
    path.write_text("\n".join(content), encoding="utf-8")
    return FileResponse(path, filename=f"{name.replace(' ', '_')}.md")


@app.get("/api/v1/media")
def media(path: str) -> FileResponse:
    p = Path(path).resolve()
    allowed = [OUTPUT_DIR.resolve(), CLIPS_DIR.resolve()]
    if not any(str(p).startswith(str(base)) for base in allowed):
        raise HTTPException(403, "Percorso non consentito")
    if not p.exists():
        raise HTTPException(404, "File non trovato")
    return FileResponse(p)


@app.post("/api/v1/clips/upload")
async def upload_clip(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "clip.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        raise HTTPException(400, "Formato video non supportato")
    safe_name = "".join(c for c in Path(file.filename or "clip.mp4").name if c.isalnum() or c in "._- ")
    dest = CLIPS_DIR / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": dest.name, "path": str(dest), "message": "Clip caricata. Per ora analisi consigliata su Colab o job locale breve."}


@app.post("/api/v1/import/colab-zip")
async def import_colab_zip(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "output.zip").suffix.lower()
    if suffix != ".zip":
        raise HTTPException(400, "Carica uno zip generato da Colab")
    tmp = DATA_DIR / f"import_{int(time.time() * 1000)}.zip"
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    extracted = 0
    try:
        with zipfile.ZipFile(tmp) as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                raw_name = member.filename.replace("\\", "/")
                name = raw_name.split("/")[-1]
                if not name:
                    continue
                dest = (OUTPUT_DIR / name).resolve()
                if not str(dest).startswith(str(OUTPUT_DIR.resolve())):
                    continue
                with zf.open(member) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1
    finally:
        tmp.unlink(missing_ok=True)
    sync = sync_outputs()
    return {"extracted": extracted, "sync": sync, "message": "Output Colab importato e sincronizzato."}


def run_job(job_id: str, req: LocalRunRequest) -> None:
    JOBS[job_id]["status"] = "running"
    video = CLIPS_DIR / req.filename
    if not video.exists():
        JOBS[job_id].update(status="failed", error="Clip non trovata")
        return
    base = video.stem
    log: list[str] = []

    def add(msg: str) -> None:
        log.append(msg)
        JOBS[job_id]["log"] = "\n".join(log)

    def run_local(command: list[str]) -> None:
        add("> " + " ".join(command))
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        add((proc.stdout or "")[-3000:])
        if proc.returncode != 0:
            add((proc.stderr or "")[-3000:])
            raise RuntimeError(f"Comando fallito: {command[1] if len(command) > 1 else command[0]}")

    csv_path = OUTPUT_DIR / f"POSIZIONIAUTO_{base}.csv"
    try:
        # 1) passo GPU (rilevamento) — su RunPod oppure in locale
        if req.use_runpod:
            from .runpod_worker import run_remote
            add("== Passo GPU su RunPod ==")
            run_remote(str(video), salto=req.salto, ogni_campo=req.ogni_campo,
                       out_dir=str(OUTPUT_DIR), log=add)
        else:
            run_local([sys.executable, str(RADAR_SCRIPT), str(video), "--salto", str(req.salto),
                       "--ogni_campo", str(req.ogni_campo), "--imgsz", "1280"]
                      + (["--no_video"] if req.no_video else []))

        # 2-4) passi leggeri SEMPRE in locale (sul CSV prodotto)
        run_local([sys.executable, str(STATS_SCRIPT), str(csv_path), "--min_rilevazioni", "12"])
        run_local([sys.executable, str(METRICS_SCRIPT), str(csv_path), "--min_rilevazioni", "12"])
        run_local([sys.executable, str(REPORT_SCRIPT), base, "--dir", str(OUTPUT_DIR)])

        sync_outputs()
        JOBS[job_id].update(status="done", log="\n".join(log))
    except Exception as exc:
        JOBS[job_id].update(status="failed", error=str(exc), log="\n".join(log))


@app.post("/api/v1/jobs/local-analysis")
def start_local_analysis(req: LocalRunRequest) -> dict[str, Any]:
    job_id = str(int(time.time() * 1000))
    JOBS[job_id] = {"id": job_id, "status": "queued", "created_at": now_iso()}
    threading.Thread(target=run_job, args=(job_id, req), daemon=True).start()
    return JOBS[job_id]


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    if job_id not in JOBS:
        raise HTTPException(404, "Job non trovato")
    return JOBS[job_id]


@app.get("/api/v1/ai/models")
def ai_models() -> dict[str, Any]:
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "ScoutLab/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("id"),
                "context_length": item.get("context_length"),
                "pricing": item.get("pricing", {}),
            }
            for item in data.get("data", [])
            if item.get("id")
        ]
        return {"source": "openrouter", "models": models}
    except Exception:
        return {
            "source": "fallback",
            "models": [
                {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini"},
                {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
                {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            ],
        }


def build_insight_context(analysis_id: int, track_db_id: int | None, profile_id: int | None = None) -> tuple[str, dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    with db() as conn:
        analysis = conn.execute("select * from analyses where id=?", (analysis_id,)).fetchone()
        if not analysis:
            raise HTTPException(404, "Analisi non trovata")
        track = None
        profile_payload = None
        profile_tracks: list[sqlite3.Row] = []
        if profile_id:
            profile = conn.execute("select * from player_profiles where id=? and analysis_id=?", (profile_id, analysis_id)).fetchone()
            if not profile:
                raise HTTPException(404, "Profilo non trovato")
            profile_tracks = conn.execute(
                """
                select t.* from tracks t
                join profile_tracks pt on pt.track_db_id = t.id
                where pt.profile_id=?
                order by t.first_time_s
                """,
                (profile_id,),
            ).fetchall()
            profile_payload = {
                "profile": dict(profile),
                "tracks": [dict(t) for t in profile_tracks],
                "aggregate": aggregate_profile_rows(profile_tracks),
            }
        if track_db_id:
            track = conn.execute("select * from tracks where id=? and analysis_id=?", (track_db_id, analysis_id)).fetchone()
            if not track:
                raise HTTPException(404, "Traccia non trovata")
    a = dict(analysis)
    t = dict(track) if track else None
    lines = [
        "Sei un analista scouting calcistico. Genera un report utile ma onesto.",
        "Non inventare identita o dati non presenti. Distingui osservazioni affidabili da limiti del campione.",
        f"Analisi: {a['title']}",
        f"Qualita dati: {a['quality_score']}/100 - {a['quality_label']} - {a['quality_notes']}",
    ]
    if profile_payload:
        p = profile_payload["profile"]
        agg = profile_payload["aggregate"]
        player = p.get("display_name") or f"Profilo #{p['id']}"
        lines += [
            f"Profilo aggregato: {player}",
            f"Numero: {p.get('jersey_number') or 'non assegnato'}",
            f"Ruolo: {p.get('role') or 'non assegnato'}",
            f"Squadra: {p.get('team') or 'non assegnata'}",
            f"Tracce unite: {agg['track_count']} | rilevazioni: {agg['n_points']} | durata osservata aggregata: {agg['observed_s']}s",
            f"Finestra temporale: {agg['first_time_s']}s - {agg['last_time_s']}s",
            f"Posizione media aggregata: x={agg['x_avg']}, y={agg['y_avg']}",
            f"Area azione aggregata: {agg['area_m2']} m2, distanza indicativa: {agg['distance_m']} m, vmax indicativa: {agg['vmax_kmh']} km/h",
            f"Confidenza aggregata: {agg['confidence']}/100",
            f"Track ID inclusi: {', '.join('#' + str(t['track_id']) for t in profile_payload['tracks'])}",
            f"Note utente: {p.get('notes') or '-'}",
        ]
    elif t:
        player = t.get("player_name") or f"Traccia #{t['track_id']}"
        lines += [
            f"Giocatore/traccia: {player}",
            f"Numero: {t.get('jersey_number') or 'non assegnato'}",
            f"Ruolo: {t.get('role') or 'non assegnato'}",
            f"Squadra stimata/corretta: {t.get('team_override') or t.get('team')}",
            f"Durata osservata: {t['duration_s']}s, rilevazioni: {t['n_points']}",
            f"Zona: {t['zone']}, posizione media: x={t['x_avg']}, y={t['y_avg']}",
            f"Area azione: {t['area_m2']} m2, distanza indicativa: {t['distance_m']} m, vmax indicativa: {t['vmax_kmh']} km/h",
            f"Confidenza traccia: {t['confidence']}/100",
            f"Note utente: {t.get('notes') or '-'}",
        ]
    lines.append("Formato: Sintesi, Indicatori osservati, Fit tattico, Rischi/limiti, Cosa rivedere nel video, Confidenza.")
    return "\n".join(lines), a, t, profile_payload


def fallback_report(prompt: str, track: dict[str, Any] | None) -> str:
    if not track:
        return (
            "Sintesi\n"
            "Analisi pronta per revisione: seleziona una traccia e assegna nome/ruolo per generare un profilo piu utile.\n\n"
            "Rischi/limiti\n"
            "Senza API key OpenRouter sto usando un fallback locale, quindi non genero valutazioni interpretative profonde."
        )
    if "track_count" in track:
        return (
            f"Sintesi\nProfilo aggregato costruito da {track['track_count']} tracce, con {track['observed_s']} secondi osservati "
            f"e confidenza {track['confidence']}/100.\n\n"
            "Indicatori osservati\n"
            f"- Posizione media aggregata: x {track['x_avg']}, y {track['y_avg']}.\n"
            f"- Area d'azione aggregata: {track['area_m2']} m2.\n"
            f"- Distanza e velocita sono indicative: {track['distance_m']} m, vmax {track['vmax_kmh']} km/h.\n\n"
            "Fit tattico\n"
            "Profilo piu robusto della singola traccia, ma ancora da validare con revisione video e ruolo assegnato.\n\n"
            "Rischi/limiti\n"
            "Le tracce unite potrebbero includere errori se il merge non e stato verificato visivamente.\n\n"
            "Cosa rivedere nel video\n"
            "Controlla continuita temporale, lato campo, postura, ricezioni e transizioni tra le tracce unite."
        )
    player = track.get("player_name") or f"Traccia #{track['track_id']}"
    return (
        f"Sintesi\n{player} e stato osservato per {track['duration_s']} secondi con confidenza {track['confidence']}/100. "
        f"La zona prevalente risulta {track['zone']}.\n\n"
        "Indicatori osservati\n"
        f"- Posizione media: x {track['x_avg']}, y {track['y_avg']}.\n"
        f"- Area d'azione: {track['area_m2']} m2.\n"
        f"- Distanza e velocita sono indicative: {track['distance_m']} m, vmax {track['vmax_kmh']} km/h.\n\n"
        "Fit tattico\n"
        "Profilo ancora da validare manualmente: assegna ruolo, numero e note video per rendere il report piu specifico.\n\n"
        "Rischi/limiti\n"
        "Campione breve e tracking da broadcast: usare come supporto allo scouting, non come verdetto.\n\n"
        "Cosa rivedere nel video\n"
        "Controlla ricezioni, orientamento del corpo, transizioni e comportamento senza palla."
    )


@app.post("/api/v1/ai/insights")
def generate_insights(req: InsightRequest) -> dict[str, Any]:
    prompt, analysis, track, profile_payload = build_insight_context(req.analysis_id, req.track_db_id, req.profile_id)
    if req.extra_context:
        prompt += "\nContesto aggiuntivo utente:\n" + req.extra_context
    api_key = req.api_key or os.environ.get("OPENROUTER_API_KEY")
    content = ""
    if api_key:
        payload = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": "Sei un analista scouting calcistico professionale, preciso e prudente."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.35,
        }
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "Scout Lab",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise HTTPException(exc.code, detail)
        except Exception as exc:
            raise HTTPException(500, f"OpenRouter non ha risposto correttamente: {exc}")
    else:
        content = fallback_report(prompt, profile_payload["aggregate"] if profile_payload else track)

    with db() as conn:
        cur = conn.execute(
            "insert into ai_reports (analysis_id, track_db_id, profile_id, model, prompt, content, created_at) values (?, ?, ?, ?, ?, ?, ?)",
            (req.analysis_id, req.track_db_id, req.profile_id, req.model, prompt, content, now_iso()),
        )
        report_id = int(cur.lastrowid)
    return {"id": report_id, "content": content, "model": req.model, "used_fallback": not bool(api_key)}
