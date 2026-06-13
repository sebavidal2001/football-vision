"""
runpod_worker.py — Esegue il passo GPU (genera_radar_auto) su un pod RunPod.

Flusso: accende un pod GPU → prepara l'ambiente (repo + modelli + deps) →
carica il video → esegue il rilevamento → riscarica il CSV → SPEGNE il pod.
Così paghi solo i minuti reali.

Configurazione (variabili d'ambiente — NON mettere la chiave nel codice):
  RUNPOD_API_KEY   (obbligatoria)  la tua API key RunPod
  RUNPOD_SSH_KEY   (consigliata)   percorso della chiave SSH PRIVATA (default ~/.ssh/id_ed25519)
  RUNPOD_GPU       (opzionale)     tipo GPU, default "NVIDIA GeForce RTX 4090"
  RUNPOD_IMAGE     (opzionale)     immagine docker base
  RUNPOD_CLOUD     (opzionale)     "COMMUNITY" (economico) o "SECURE"

Test da solo:
  set RUNPOD_API_KEY=...   (Windows)  /  export RUNPOD_API_KEY=...  (bash)
  python runpod_worker.py  path/al/video.mp4
"""
from __future__ import annotations

import os
import sys
import time
import posixpath
from pathlib import Path
from typing import Callable

REPO_URL = "https://github.com/sebavidal2001/football-vision.git"
MODELS = {
    "vista_tattica/yolo-football-pitch-detection.pt":
        "https://huggingface.co/martinjolif/yolo-football-pitch-detection/resolve/main/yolo-football-pitch-detection.pt",
    "vista_tattica/giocatori_calcio.pt":
        "https://huggingface.co/uisikdag/yolo-v8-football-players-detection/resolve/main/best.pt",
}
REMOTE_ROOT = "/workspace/fv"
DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
DEFAULT_GPU = "NVIDIA GeForce RTX 4090"
# GPU di ripiego se la preferita non è disponibile (dalla più conveniente alla più potente)
GPU_FALLBACK = [
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 3090",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A4000",
    "NVIDIA GeForce RTX 4080",
    "NVIDIA A40",
    "NVIDIA L4",
    "NVIDIA L40S",
]


def _log(cb: Callable[[str], None] | None, msg: str) -> None:
    print(msg, flush=True)
    if cb:
        cb(msg)


def _wait_running(runpod, pod_id: str, log, timeout: int = 600) -> tuple[str, int]:
    """Attende che il pod sia avviato e ritorna (ip, porta) SSH (porta 22 pubblica)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        pod = runpod.get_pod(pod_id)
        runtime = (pod or {}).get("runtime") or {}
        ports = runtime.get("ports") or []
        for p in ports:
            if str(p.get("privatePort")) == "22" and p.get("ip") and p.get("publicPort"):
                ip, port = p["ip"], int(p["publicPort"])
                _log(log, f"   SSH disponibile: {ip}:{port}")
                return ip, port
        _log(log, "   ...attendo avvio pod / porta SSH")
        time.sleep(10)
    raise TimeoutError("Pod non ha esposto la porta SSH in tempo")


def _ssh_connect(ip: str, port: int, key_path: str, log, timeout: int = 240):
    import paramiko
    key_path = os.path.expanduser(key_path)
    pkey = None
    if os.path.exists(key_path):
        for loader in (paramiko.Ed25519Key, paramiko.RSAKey):
            try:
                pkey = loader.from_private_key_file(key_path)
                break
            except Exception:
                continue
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            client.connect(ip, port=port, username="root", pkey=pkey,
                           key_filename=None if pkey else key_path, timeout=20)
            _log(log, "   SSH connesso.")
            return client
        except Exception as exc:
            _log(log, f"   ...SSH non pronto ({exc}); riprovo")
            time.sleep(10)
    raise TimeoutError("Impossibile connettersi in SSH al pod")


def _exec(ssh, cmd: str, log) -> None:
    _log(log, f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    for line in iter(stdout.readline, ""):
        if line:
            _log(log, "   " + line.rstrip())
    code = stdout.channel.recv_exit_status()
    if code != 0:
        err = stderr.read().decode("utf-8", "replace")[-2000:]
        raise RuntimeError(f"Comando remoto fallito (exit {code}): {err}")


def _setup_script() -> str:
    dl = "\n".join(
        f'[ -f {dst} ] || wget -q -O {dst} "{url}"' for dst, url in MODELS.items()
    )
    return (
        "set -e\n"
        "mkdir -p /workspace && cd /workspace\n"
        f"if [ ! -d fv ]; then git clone -q {REPO_URL} fv; fi\n"
        "cd fv && git pull -q || true\n"
        "mkdir -p vista_tattica clips_input output\n"
        "pip install -q ultralytics supervision scikit-learn 2>/dev/null\n"
        f"{dl}\n"
        'echo SETUP_OK'
    )


def run_remote(video_path: str, salto: int = 3, ogni_campo: int = 2, imgsz: int = 1280,
               out_dir: str | None = None, log: Callable[[str], None] | None = None,
               keep_pod: bool = False) -> str:
    """Esegue genera_radar_auto su RunPod e ritorna il path locale del CSV scaricato."""
    import runpod
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise RuntimeError("RUNPOD_API_KEY non impostata (variabile d'ambiente).")
    runpod.api_key = api_key

    video_path = str(video_path)
    out_dir = out_dir or str(Path(video_path).resolve().parents[1] / "output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    base = Path(video_path).stem
    gpu = os.environ.get("RUNPOD_GPU", DEFAULT_GPU)
    image = os.environ.get("RUNPOD_IMAGE", DEFAULT_IMAGE)
    cloud = os.environ.get("RUNPOD_CLOUD", "COMMUNITY")
    key_path = os.environ.get("RUNPOD_SSH_KEY", "~/.ssh/id_ed25519")

    # ordine GPU: prima la preferita, poi i ripieghi (senza duplicati)
    gpu_order = [gpu] + [g for g in GPU_FALLBACK if g != gpu]
    cloud_order = [cloud] + (["SECURE"] if cloud != "SECURE" else ["COMMUNITY"])

    _log(log, "▶ Cerco una GPU disponibile su RunPod...")
    pod = None
    last_err = None
    for cl in cloud_order:
        for g in gpu_order:
            try:
                _log(log, f"   provo {g} ({cl})...")
                pod = runpod.create_pod(
                    name="football-vision",
                    image_name=image,
                    gpu_type_id=g,
                    cloud_type=cl,
                    container_disk_in_gb=25,
                    volume_in_gb=0,
                    ports="22/tcp",
                    support_public_ip=True,
                )
                _log(log, f"   ✅ Pod avviato su {g} ({cl})")
                break
            except Exception as exc:
                last_err = exc
                msg = str(exc).lower()
                if "resource" in msg or "not have" in msg or "availab" in msg:
                    continue  # nessuna disponibilità: prova la prossima
                raise  # errore diverso (es. auth) -> fermati subito
        if pod:
            break
    if not pod:
        raise RuntimeError(f"Nessuna GPU disponibile al momento su RunPod. Ultimo errore: {last_err}")
    pod_id = pod["id"]
    _log(log, f"   Pod creato: {pod_id}")
    ssh = None
    try:
        ip, port = _wait_running(runpod, pod_id, log)
        ssh = _ssh_connect(ip, port, key_path, log)

        _log(log, "▶ Preparo l'ambiente sul pod (repo + modelli + deps)...")
        _exec(ssh, _setup_script(), log)

        sftp = ssh.open_sftp()
        remote_video = posixpath.join(REMOTE_ROOT, "clips_input", Path(video_path).name)
        _log(log, f"▶ Carico il video sul pod ({Path(video_path).stat().st_size/1e6:.0f} MB)...")
        sftp.put(video_path, remote_video)

        cmd = (f"cd {REMOTE_ROOT} && python vista_tattica/genera_radar_auto.py "
               f"'{remote_video}' --salto {salto} --ogni_campo {ogni_campo} --imgsz {imgsz} --no_video")
        _log(log, "▶ Eseguo il rilevamento su GPU...")
        _exec(ssh, cmd, log)

        remote_csv = posixpath.join(REMOTE_ROOT, "output", f"POSIZIONIAUTO_{base}.csv")
        local_csv = os.path.join(out_dir, f"POSIZIONIAUTO_{base}.csv")
        _log(log, "▶ Scarico il CSV dei risultati...")
        sftp.get(remote_csv, local_csv)
        sftp.close()
        _log(log, f"✅ Fatto: {local_csv}")
        return local_csv
    finally:
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass
        if not keep_pod:
            _log(log, "▶ Spengo il pod (per non pagare oltre)...")
            try:
                runpod.terminate_pod(pod_id)
                _log(log, "   Pod terminato.")
            except Exception as exc:
                _log(log, f"   ⚠ ATTENZIONE: non sono riuscito a terminare il pod {pod_id}: {exc}")
                _log(log, "   Spegnilo a mano dal sito RunPod per non pagare!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python runpod_worker.py <video.mp4>")
        sys.exit(1)
    run_remote(sys.argv[1])
