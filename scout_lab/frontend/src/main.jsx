import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  Brain,
  CheckCircle2,
  ChevronRight,
  Cloud,
  Clock3,
  Download,
  Eye,
  FileVideo,
  Gauge,
  GitMerge,
  Layers3,
  Link2,
  PlayCircle,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  UsersRound,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './styles.css';

const SERVER = 'http://127.0.0.1:8000';
const API = `${SERVER}/api/v1`;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

function fmt(value, suffix = '') {
  if (value === null || value === undefined || value === '') return 'n/d';
  const n = Number(value);
  if (!Number.isNaN(n)) return `${Math.round(n * 10) / 10}${suffix}`;
  return `${value}${suffix}`;
}

function useMeasuredSize() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!ref.current) return undefined;
    const element = ref.current;
    const update = () => {
      const rect = element.getBoundingClientRect();
      setSize({
        width: Math.max(1, Math.floor(rect.width)),
        height: Math.max(1, Math.floor(rect.height)),
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  return [ref, size];
}

function App() {
  const [analyses, setAnalyses] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [selectedTrackId, setSelectedTrackId] = useState(null);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState(localStorage.getItem('openrouter_key') || '');
  const [insight, setInsight] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [uploadedClip, setUploadedClip] = useState('');
  const [useRunpod, setUseRunpod] = useState(false);
  const [ytUrl, setYtUrl] = useState('');
  const [ytStart, setYtStart] = useState('00:00:00');
  const [ytEnd, setYtEnd] = useState('00:01:00');
  const [job, setJob] = useState(null);
  const [selectedTrackIds, setSelectedTrackIds] = useState(new Set());
  const [reviewMode, setReviewMode] = useState('reviewable');
  const [minDuration, setMinDuration] = useState(6);
  const [minConfidence, setMinConfidence] = useState(35);
  const [selectedProfileId, setSelectedProfileId] = useState(null);
  const [profileDetail, setProfileDetail] = useState(null);
  const [mergeSuggestions, setMergeSuggestions] = useState([]);
  const [identitySuggestions, setIdentitySuggestions] = useState({ profiles: 0, unassigned_tracks: 0, suggestions: [] });
  const [videoTime, setVideoTime] = useState(0);
  const [videoAsset, setVideoAsset] = useState('radar');
  const videoRef = useRef(null);
  const [pitchRef, pitchSize] = useMeasuredSize();
  const [durationChartRef, durationChartSize] = useMeasuredSize();

  async function load() {
    const list = await api('/analyses');
    setAnalyses(list);
    if (!selectedId && list[0]) setSelectedId(list[0].id);
  }

  async function loadModels() {
    const data = await api('/ai/models');
    setModels(data.models || []);
    if (!model && data.models?.[0]) setModel(data.models[0].id);
  }

  useEffect(() => {
    load().catch((e) => setNotice(e.message));
    loadModels().catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    api(`/analyses/${selectedId}`)
      .then((data) => {
        setDetail(data);
        setSelectedTrackId(data.tracks?.[0]?.id || null);
        setSelectedTrackIds(new Set(data.tracks?.[0] ? [data.tracks[0].id] : []));
        setSelectedProfileId(data.profiles?.[0]?.id || null);
        setInsight(data.reports?.[0]?.content || '');
        setVideoAsset(data.assets?.clip ? 'clip' : 'radar');
        api(`/analyses/${selectedId}/merge-suggestions?limit=18`)
          .then(setMergeSuggestions)
          .catch(() => setMergeSuggestions([]));
        api(`/analyses/${selectedId}/identity-suggestions?limit=18`)
          .then(setIdentitySuggestions)
          .catch(() => setIdentitySuggestions({ profiles: 0, unassigned_tracks: 0, suggestions: [] }));
      })
      .catch((e) => setNotice(e.message));
  }, [selectedId]);

  const selectedTrack = useMemo(
    () => detail?.tracks?.find((track) => track.id === selectedTrackId),
    [detail, selectedTrackId],
  );

  useEffect(() => {
    if (!selectedProfileId) {
      setProfileDetail(null);
      return;
    }
    api(`/profiles/${selectedProfileId}`)
      .then(setProfileDetail)
      .catch((e) => setNotice(e.message));
  }, [selectedProfileId]);

  const filteredTracks = useMemo(() => {
    const tracks = detail?.tracks || [];
    const byMode = tracks.filter((track) => {
      if (reviewMode === 'identified') return Boolean(track.player_name || track.jersey_number || track.role);
      if (reviewMode === 'all') return true;
      return Number(track.duration_s || 0) >= minDuration && Number(track.confidence || 0) >= minConfidence;
    });
    if (!query.trim()) return byMode;
    const q = query.toLowerCase();
    return byMode.filter((t) =>
      [t.track_id, t.player_name, t.jersey_number, t.role, t.zone]
        .join(' ')
        .toLowerCase()
        .includes(q),
    );
  }, [detail, query, reviewMode, minDuration, minConfidence]);

  const reviewStats = useMemo(() => {
    const tracks = detail?.tracks || [];
    const reviewable = tracks.filter((track) => Number(track.duration_s || 0) >= minDuration && Number(track.confidence || 0) >= minConfidence);
    const identified = tracks.filter((track) => Boolean(track.player_name || track.jersey_number || track.role));
    return { total: tracks.length, reviewable: reviewable.length, identified: identified.length };
  }, [detail, minDuration, minConfidence]);

  const topTracks = useMemo(
    () => (detail?.tracks || []).slice(0, 14).map((t) => ({ name: `#${t.track_id}`, durata: t.duration_s, conf: t.confidence })),
    [detail],
  );

  const pitchPoints = useMemo(
    () => (detail?.tracks || []).slice(0, 120).map((t) => ({ ...t, x: t.x_avg, y: t.y_avg })),
    [detail],
  );

  const videoOptions = useMemo(
    () => [
      { id: 'clip', label: 'Clip', url: detail?.assets?.clip },
      { id: 'radar', label: 'Radar', url: detail?.assets?.radar },
    ].filter((item) => item.url),
    [detail],
  );

  const activeVideoUrl = useMemo(() => {
    const preferred = videoOptions.find((item) => item.id === videoAsset) || videoOptions[0];
    return preferred?.url || null;
  }, [videoOptions, videoAsset]);

  const selectedTimelineTracks = useMemo(() => {
    const tracks = filteredTracks.length ? filteredTracks : detail?.tracks || [];
    const selected = tracks.filter((track) => selectedTrackIds.has(track.id));
    const profileTracks = profileDetail?.tracks || [];
    const merged = [...profileTracks, ...selected, ...tracks.slice(0, 18)];
    const byId = new Map();
    merged.forEach((track) => byId.set(track.id, track));
    return [...byId.values()].sort((a, b) => a.first_time_s - b.first_time_s || b.n_points - a.n_points).slice(0, 28);
  }, [detail, filteredTracks, selectedTrackIds, profileDetail]);

  const activeWindow = useMemo(() => {
    if (profileDetail?.aggregate) {
      return {
        label: profileDetail.profile.display_name || `Profilo #${profileDetail.profile.id}`,
        start: profileDetail.aggregate.first_time_s || 0,
        end: profileDetail.aggregate.last_time_s || 0,
      };
    }
    if (selectedTrack) {
      return {
        label: selectedTrack.player_name || `Track ID #${selectedTrack.track_id}`,
        start: selectedTrack.first_time_s || 0,
        end: selectedTrack.last_time_s || 0,
      };
    }
    return null;
  }, [profileDetail, selectedTrack]);

  function seekVideo(seconds, shouldPlay = true) {
    const next = Math.max(0, Number(seconds) || 0);
    setVideoTime(next);
    if (!videoRef.current) return;
    videoRef.current.currentTime = next;
    if (shouldPlay) videoRef.current.play().catch(() => {});
  }

  async function sync() {
    setBusy(true);
    try {
      await api('/sync', { method: 'POST' });
      await load();
      setNotice('Output sincronizzati.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadClip(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setBusy(true);
    try {
      const data = await api('/clips/upload', { method: 'POST', body: form });
      setUploadedClip(data.filename);
      setNotice(`${data.filename} caricato. Analizzalo su Colab o avvia un job locale breve.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  }

  async function importColabZip(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setBusy(true);
    try {
      const data = await api('/import/colab-zip', { method: 'POST', body: form });
      await load();
      setNotice(`${data.message} File estratti: ${data.extracted}.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  }

  async function startLocalJob() {
    if (!uploadedClip) {
      setNotice('Carica prima una clip breve.');
      return;
    }
    setBusy(true);
    try {
      const data = await api('/jobs/local-analysis', {
        method: 'POST',
        body: JSON.stringify({ filename: uploadedClip, salto: 3, ogni_campo: 2, no_video: true, use_runpod: useRunpod }),
      });
      setJob(data);
      setNotice(useRunpod
        ? 'Job avviato su RunPod (accende il pod GPU, esegue, lo spegne). Puoi seguirlo nel log.'
        : 'Job locale avviato. Su CPU puo essere lento: usa solo clip brevi.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function startYoutubeJob() {
    if (!ytUrl) {
      setNotice('Incolla un link YouTube.');
      return;
    }
    setBusy(true);
    try {
      const data = await api('/jobs/youtube', {
        method: 'POST',
        body: JSON.stringify({
          url: ytUrl,
          inizio: ytStart || '00:00:00',
          fine: ytEnd || '00:01:00',
          use_runpod: useRunpod,
        }),
      });
      setJob(data);
      setNotice('Scarico da YouTube e poi analizzo. Segui lo stato del job qui sotto.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const data = await api(`/jobs/${job.id}`);
        setJob(data);
        if (data.status === 'done') {
          await load();
          setNotice('Job locale completato e output sincronizzati.');
        }
        if (data.status === 'failed') setNotice(`Job fallito: ${data.error}`);
      } catch (e) {
        setNotice(e.message);
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [job]);

  async function saveTrack(formData) {
    if (!selectedTrack) return;
    const payload = {
      player_name: formData.get('player_name'),
      jersey_number: formData.get('jersey_number'),
      role: formData.get('role'),
      team_override: formData.get('team_override') ? Number(formData.get('team_override')) : null,
      notes: formData.get('notes'),
    };
    setBusy(true);
    try {
      const updated = await api(`/tracks/${selectedTrack.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      setDetail((old) => ({
        ...old,
        tracks: old.tracks.map((track) => (track.id === updated.id ? updated : track)),
      }));
      setNotice('Profilo traccia aggiornato.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleTrack(id) {
    setSelectedTrackIds((old) => {
      const next = new Set(old);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function createProfileFromSelection() {
    if (!detail) return;
    const ids = Array.from(selectedTrackIds);
    if (!ids.length && selectedTrack) ids.push(selectedTrack.id);
    if (!ids.length) {
      setNotice('Seleziona almeno una traccia da unire.');
      return;
    }
    const seed = selectedTrack || detail.tracks.find((track) => track.id === ids[0]);
    setBusy(true);
    try {
      const created = await api('/profiles', {
        method: 'POST',
        body: JSON.stringify({
          analysis_id: detail.id,
          track_db_ids: ids,
          display_name: seed?.player_name || '',
          jersey_number: seed?.jersey_number || '',
          role: seed?.role || '',
          team: seed?.team_override || seed?.team || null,
          notes: seed?.notes || '',
        }),
      });
      const refreshed = await api(`/analyses/${detail.id}`);
      setDetail(refreshed);
      setSelectedProfileId(created.id);
      const suggestions = await api(`/analyses/${detail.id}/merge-suggestions?limit=18`);
      setMergeSuggestions(suggestions);
      const identity = await api(`/analyses/${detail.id}/identity-suggestions?limit=18`);
      setIdentitySuggestions(identity);
      setNotice(`Profilo aggregato creato con ${ids.length} tracce.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function createIdentityFromSelectedTrack() {
    if (!detail || !selectedTrack) return;
    setBusy(true);
    try {
      const created = await api('/profiles', {
        method: 'POST',
        body: JSON.stringify({
          analysis_id: detail.id,
          track_db_ids: [selectedTrack.id],
          display_name: selectedTrack.player_name || '',
          jersey_number: selectedTrack.jersey_number || '',
          role: selectedTrack.role || '',
          team: selectedTrack.team_override || selectedTrack.team || null,
          notes: selectedTrack.notes || '',
        }),
      });
      const refreshed = await api(`/analyses/${detail.id}`);
      setDetail(refreshed);
      setSelectedProfileId(created.id);
      const identity = await api(`/analyses/${detail.id}/identity-suggestions?limit=18`);
      setIdentitySuggestions(identity);
      setNotice(`Identità creata da Track ID #${selectedTrack.track_id}. Ora controlla i suggerimenti.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function applyIdentitySuggestion(suggestion) {
    if (!detail) return;
    setBusy(true);
    try {
      const updated = await api(`/profiles/${suggestion.profile.id}/tracks`, {
        method: 'POST',
        body: JSON.stringify({ track_db_id: suggestion.track.id, propagate_identity: true }),
      });
      const refreshed = await api(`/analyses/${detail.id}`);
      setDetail(refreshed);
      setSelectedTrackId(suggestion.track.id);
      setSelectedProfileId(suggestion.profile.id);
      setProfileDetail(updated);
      const identity = await api(`/analyses/${detail.id}/identity-suggestions?limit=18`);
      setIdentitySuggestions(identity);
      const suggestions = await api(`/analyses/${detail.id}/merge-suggestions?limit=18`);
      setMergeSuggestions(suggestions);
      setNotice(`Track ID #${suggestion.track.track_id} agganciato a ${suggestion.profile.display_name || 'identità selezionata'}.`);
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  function applySuggestion(suggestion) {
    const ids = suggestion.ordered_track_ids || suggestion.track_ids;
    setSelectedTrackIds(new Set(ids));
    setSelectedTrackId(ids[0]);
    setSelectedProfileId(null);
    const first = detail?.tracks?.find((track) => track.id === ids[0]);
    if (first) seekVideo(first.first_time_s, false);
    setNotice(`Suggerimento selezionato: ${suggestion.track_labels.join(' + ')}.`);
  }

  async function generateInsight() {
    if (!detail || !model) return;
    localStorage.setItem('openrouter_key', apiKey);
    setBusy(true);
    setInsight('');
    try {
      const data = await api('/ai/insights', {
        method: 'POST',
        body: JSON.stringify({
          analysis_id: detail.id,
          track_db_id: selectedProfileId ? null : selectedTrack?.id,
          profile_id: selectedProfileId || null,
          model,
          api_key: apiKey || null,
        }),
      });
      setInsight(data.content);
      setNotice(data.used_fallback ? 'Insight generato in fallback locale: aggiungi API key per OpenRouter.' : 'Insight generato con OpenRouter.');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark"><Eye size={22} /></div>
          <div>
            <p className="eyebrow">Football Vision</p>
            <h1>Scout Lab</h1>
          </div>
        </div>

        <label className="upload-tile">
          <Upload size={18} />
          <span>Carica clip</span>
          <input type="file" accept="video/*" onChange={uploadClip} />
        </label>

        <div className="yt-form">
          <p className="yt-title">Da YouTube (link + ore:minuti:secondi)</p>
          <input className="yt-input" placeholder="https://youtu.be/..." value={ytUrl} onChange={(e) => setYtUrl(e.target.value)} />
          <div className="yt-times">
            <input className="yt-input" placeholder="da  00:28:00" value={ytStart} onChange={(e) => setYtStart(e.target.value)} />
            <input className="yt-input" placeholder="a  00:32:00" value={ytEnd} onChange={(e) => setYtEnd(e.target.value)} />
          </div>
          <button className="ghost-button" onClick={startYoutubeJob} disabled={busy || !ytUrl}>
            <Download size={16} />
            Scarica e analizza
          </button>
        </div>

        <label className="ghost-upload">
          <Download size={17} />
          <span>Importa zip Colab</span>
          <input type="file" accept=".zip" onChange={importColabZip} />
        </label>

        <button className="ghost-button" onClick={sync} disabled={busy}>
          <RefreshCw size={17} />
          Sincronizza output
        </button>

        <button className="ghost-button" onClick={startLocalJob} disabled={busy || !uploadedClip}>
          <Activity size={17} />
          {useRunpod ? 'Analizza su RunPod (GPU)' : 'Job locale breve'}
        </button>

        <label className="ghost-button" style={{ cursor: 'pointer', gap: 8 }}>
          <input type="checkbox" checked={useRunpod} onChange={(e) => setUseRunpod(e.target.checked)} />
          Esegui su RunPod (GPU)
        </label>

        {job && (
          <div className="job-chip">
            <span>Job {job.id}</span>
            <strong>{job.status}</strong>
          </div>
        )}

        <section className="analysis-list">
          <div className="section-title">Analisi</div>
          {analyses.map((analysis) => (
            <button
              className={`analysis-item ${analysis.id === selectedId ? 'active' : ''}`}
              key={analysis.id}
              onClick={() => setSelectedId(analysis.id)}
            >
              <FileVideo size={17} />
              <span>{analysis.title}</span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!analyses.length && <p className="muted">Nessun output trovato. Esegui Colab e scarica lo zip in `output/`.</p>}
        </section>

        <div className="colab-note">
          <Cloud size={18} />
          <p>Colab resta il worker GPU: esporta lo zip in `output/`, poi sincronizza.</p>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Clip review</p>
            <h2>{detail?.title || 'Seleziona una clip'}</h2>
          </div>
          <div className="quality-pill">
            <ShieldCheck size={18} />
            <span>{detail ? `${detail.quality_score}/100` : '--'}</span>
            <small>{detail?.quality_label || 'Quality score'}</small>
          </div>
        </header>

        {notice && (
          <div className="notice" onClick={() => setNotice('')}>
            <CheckCircle2 size={17} />
            {notice}
          </div>
        )}

        {detail && (
          <>
            <section className="metric-grid">
              <Metric icon={<Activity />} label="Durata clip" value={fmt(detail.duration_s, 's')} />
              <Metric icon={<Layers3 />} label="Tracce rilevate" value={detail.track_count} />
              <Metric icon={<Gauge />} label="Frame analizzati" value={detail.frame_count} />
              <Metric icon={<Sparkles />} label="ID tracking attivo" value={selectedTrack ? `#${selectedTrack.track_id}` : 'n/d'} />
            </section>

            {detail.report && (detail.report.formazione || detail.report.team_metrics?.length > 0) && (
              <section className="results-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Risultati tattici (affidabili)</p>
                    <h3>Report squadra</h3>
                  </div>
                  {detail.report.report_pdf && (
                    <a className="download-link" href={`${SERVER}${detail.report.report_pdf}`} target="_blank" rel="noreferrer">
                      Scarica PDF
                    </a>
                  )}
                </div>

                {detail.report.team_metrics?.length > 0 && (
                  <table className="team-metrics">
                    <thead>
                      <tr><th></th><th>Squadra 1</th><th>Squadra 2</th></tr>
                    </thead>
                    <tbody>
                      {[
                        ['Modulo', 'modulo'],
                        ['Possesso %', 'possesso_pct'],
                        ['Ampiezza (m)', 'ampiezza_media_m'],
                        ['Profondità (m)', 'profondita_media_m'],
                        ['Compattezza (m)', 'compattezza_media_m'],
                      ].map(([label, key]) => (
                        <tr key={key}>
                          <td>{label}</td>
                          <td>{detail.report.team_metrics.find((r) => String(r.squadra) === '1')?.[key] ?? '-'}</td>
                          <td>{detail.report.team_metrics.find((r) => String(r.squadra) === '2')?.[key] ?? '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                <div className="results-gallery">
                  {[
                    ['Formazione / modulo', detail.report.formazione],
                    ['Andamento tattico', detail.report.andamento],
                    ['Confronto giocatori', detail.report.dashboard],
                    ['Heatmap Squadra 1', detail.report.heatmap_team1],
                    ['Heatmap Squadra 2', detail.report.heatmap_team2],
                  ].filter(([, url]) => url).map(([label, url]) => (
                    <figure key={label}>
                      <a href={`${SERVER}${url}`} target="_blank" rel="noreferrer">
                        <img src={`${SERVER}${url}`} alt={label} loading="lazy" />
                      </a>
                      <figcaption>{label}</figcaption>
                    </figure>
                  ))}
                </div>
              </section>
            )}

            <section className="main-grid">
              <div className="pitch-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Mappa media</p>
                    <h3>Distribuzione tracce</h3>
                  </div>
                  <span>{detail.quality_notes}</span>
                </div>
                <div className="pitch" ref={pitchRef}>
                  {pitchSize.width > 1 && pitchSize.height > 1 && (
                    <ScatterChart width={pitchSize.width} height={pitchSize.height} margin={{ top: 16, right: 16, bottom: 16, left: 16 }}>
                      <CartesianGrid stroke="rgba(255,255,255,.12)" />
                      <XAxis type="number" dataKey="x" domain={[0, 120]} hide />
                      <YAxis type="number" dataKey="y" domain={[70, 0]} hide />
                      <Tooltip content={<PitchTooltip />} />
                      <Scatter data={pitchPoints} onClick={(point) => setSelectedTrackId(point.id)}>
                        {pitchPoints.map((entry) => (
                          <Cell
                            key={entry.id}
                            fill={(entry.team_override || entry.team) === 2 ? '#ff5d48' : '#4fb3ff'}
                            opacity={entry.id === selectedTrackId ? 1 : 0.62}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  )}
                </div>
              </div>

              <div className="profile-panel">
                <div className="panel-heading compact">
                  <div>
                    <p className="eyebrow">Track review</p>
                    <h3>{selectedTrack?.player_name || (selectedTrack ? `Track ID #${selectedTrack.track_id}` : 'Nessuna traccia')}</h3>
                  </div>
                  <UserRound />
                </div>

                {selectedTrack && (
                  <form
                    className="profile-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      saveTrack(new FormData(event.currentTarget));
                    }}
                  >
                    <div className="form-row">
                      <label>Nome</label>
                      <input name="player_name" defaultValue={selectedTrack.player_name || ''} placeholder="es. Lautaro Martinez" />
                    </div>
                    <div className="form-split">
                      <div className="form-row">
                        <label>Numero</label>
                        <input name="jersey_number" defaultValue={selectedTrack.jersey_number || ''} placeholder="10" />
                      </div>
                      <div className="form-row">
                        <label>Ruolo</label>
                        <select name="role" defaultValue={selectedTrack.role || ''}>
                          <option value="">Da assegnare</option>
                          <option>Portiere</option>
                          <option>Terzino</option>
                          <option>Braccetto</option>
                          <option>Centrale</option>
                          <option>Quinto</option>
                          <option>Mediano</option>
                          <option>Mezzala</option>
                          <option>Trequartista</option>
                          <option>Esterno</option>
                          <option>Seconda punta</option>
                          <option>Attaccante</option>
                        </select>
                      </div>
                    </div>
                    <div className="form-row">
                      <label>Squadra corretta</label>
                      <select name="team_override" defaultValue={selectedTrack.team_override || ''}>
                        <option value="">Usa stimata ({selectedTrack.team})</option>
                        <option value="1">Squadra 1</option>
                        <option value="2">Squadra 2</option>
                      </select>
                    </div>
                    <div className="form-row">
                      <label>Note scout</label>
                      <textarea name="notes" defaultValue={selectedTrack.notes || ''} placeholder="Movimenti, postura, decisioni, duelli..." />
                    </div>
                    <button className="primary-button" disabled={busy}>
                      <Save size={17} />
                      Salva revisione
                    </button>
                    <button type="button" className="secondary-button" onClick={createProfileFromSelection} disabled={busy}>
                      <GitMerge size={17} />
                      Crea profilo aggregato
                    </button>
                    <button type="button" className="secondary-button" onClick={createIdentityFromSelectedTrack} disabled={busy}>
                      <UserRound size={17} />
                      Crea identità da questo ID
                    </button>
                  </form>
                )}
              </div>
            </section>

            <section className="video-grid">
              <div className="video-panel">
                <div className="panel-heading compact">
                  <div>
                    <p className="eyebrow">Controllo video</p>
                    <h3>Radar / clip importata</h3>
                  </div>
                  <FileVideo size={22} />
                </div>
                {selectedTrack && (
                  <div className="track-focus-card">
                    <span>ID tracking selezionato</span>
                    <strong>#{selectedTrack.track_id}</strong>
                    <small>{fmt(selectedTrack.first_time_s, 's')} - {fmt(selectedTrack.last_time_s, 's')} · {fmt(selectedTrack.duration_s, 's')} · {selectedTrack.zone}</small>
                  </div>
                )}
                {videoOptions.length > 0 && (
                  <div className="video-source-tabs">
                    {videoOptions.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={item.id === videoAsset ? 'active' : ''}
                        onClick={() => setVideoAsset(item.id)}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
                {activeVideoUrl ? (
                  <video
                    ref={videoRef}
                    controls
                    src={`${SERVER}${activeVideoUrl}`}
                    onLoadedMetadata={(event) => {
                      if (videoTime > 0) event.currentTarget.currentTime = videoTime;
                    }}
                    onTimeUpdate={(event) => setVideoTime(event.currentTarget.currentTime)}
                  />
                ) : (
                  <div className="empty-media">Nessun video disponibile. Importa uno zip Colab con `RADARAUTO_*.mp4` o collega la clip originale.</div>
                )}
                <div className="video-actions">
                  <button type="button" onClick={() => activeWindow && seekVideo(activeWindow.start)} disabled={!activeWindow || !activeVideoUrl}>
                    <PlayCircle size={16} />
                    Inizio finestra
                  </button>
                  <button type="button" onClick={() => activeWindow && seekVideo(Math.max(activeWindow.end - 2, activeWindow.start))} disabled={!activeWindow || !activeVideoUrl}>
                    <Clock3 size={16} />
                    Fine azione
                  </button>
                </div>
              </div>

              <div className="aggregate-panel">
                <div className="panel-heading compact">
                  <div>
                    <p className="eyebrow">Identità giocatore</p>
                    <h3>Identity Engine</h3>
                  </div>
                  <UsersRound size={22} />
                </div>
                <div className="identity-status">
                  <span>{identitySuggestions.profiles || 0} identità</span>
                  <span>{identitySuggestions.unassigned_tracks || 0} Track ID da valutare</span>
                </div>
                <div className="profile-list">
                  {(detail.profiles || []).map((profile) => (
                    <button
                      key={profile.id}
                      className={`profile-row ${profile.id === selectedProfileId ? 'active' : ''}`}
                      onClick={() => setSelectedProfileId(profile.id)}
                    >
                      <span>{profile.display_name || `Profilo #${profile.id}`}</span>
                      <small>{profile.track_count} tracce · {fmt(profile.observed_s, 's')} · {Math.round(profile.avg_confidence || 0)}%</small>
                    </button>
                  ))}
                  {!detail.profiles?.length && <p className="muted">Seleziona più tracce e crea un profilo aggregato.</p>}
                </div>
                {profileDetail && (
                  <div className="profile-summary">
                    <b>{profileDetail.profile.display_name || `Profilo #${profileDetail.profile.id}`}</b>
                    <span>{profileDetail.aggregate.track_count} tracce unite</span>
                    <span>{fmt(profileDetail.aggregate.observed_s, 's')} osservati</span>
                    <span>{profileDetail.aggregate.confidence}/100 confidenza</span>
                    <a className="download-link" href={`${API}/profiles/${profileDetail.profile.id}/export.md`}>
                      <Download size={15} />
                      Export MD
                    </a>
                  </div>
                )}
                <div className="suggestions-block">
                  <div className="mini-heading">
                    <ShieldCheck size={15} />
                    Propagazione identità
                  </div>
                  <div className="suggestions-list">
                    {(identitySuggestions.suggestions || []).slice(0, 6).map((suggestion) => (
                      <button
                        key={`${suggestion.profile.id}-${suggestion.track.id}`}
                        className={`suggestion-row identity-${suggestion.status}`}
                        onClick={() => applyIdentitySuggestion(suggestion)}
                      >
                        <span>{suggestion.profile.display_name || `Profilo #${suggestion.profile.id}`} -&gt; Track ID #{suggestion.track.track_id}</span>
                        <small>{suggestion.score}/100 · {suggestion.reason}</small>
                      </button>
                    ))}
                    {!(identitySuggestions.suggestions || []).length && (
                      <p className="muted">{identitySuggestions.profiles ? 'Nessun aggancio identità forte: continua con review manuale.' : 'Crea una prima identità da un Track ID verificato.'}</p>
                    )}
                  </div>
                </div>
                <div className="suggestions-block">
                  <div className="mini-heading">
                    <Sparkles size={15} />
                    Suggerimenti merge
                  </div>
                  <div className="suggestions-list">
                    {mergeSuggestions.slice(0, 6).map((suggestion, index) => (
                      <button key={`${suggestion.track_ids.join('-')}-${index}`} className="suggestion-row" onClick={() => applySuggestion(suggestion)}>
                        <span>{suggestion.track_labels.join(' + ')}</span>
                        <small>{suggestion.score}/100 · {suggestion.reason}</small>
                      </button>
                    ))}
                    {!mergeSuggestions.length && <p className="muted">Nessun suggerimento forte: usa selezione manuale.</p>}
                  </div>
                </div>
              </div>
            </section>

            <TimelineReview
              detail={detail}
              tracks={selectedTimelineTracks}
              selectedTrackId={selectedTrackId}
              selectedTrackIds={selectedTrackIds}
              activeWindow={activeWindow}
              videoTime={videoTime}
              onSelectTrack={(track) => {
                setSelectedTrackId(track.id);
                setSelectedProfileId(null);
              }}
              onToggleTrack={toggleTrack}
              onSeek={seekVideo}
            />

            <section className="lower-grid">
              <div className="tracks-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Giocatori osservati</p>
                    <h3>Track ID principali ({selectedTrackIds.size} selezionati)</h3>
                  </div>
                  <div className="search-box">
                    <Search size={16} />
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cerca traccia, nome, ruolo" />
                  </div>
                </div>
                <div className="review-controls">
                  <div className="segmented-control">
                    <button type="button" className={reviewMode === 'reviewable' ? 'active' : ''} onClick={() => setReviewMode('reviewable')}>
                      Revisionabili
                    </button>
                    <button type="button" className={reviewMode === 'identified' ? 'active' : ''} onClick={() => setReviewMode('identified')}>
                      Identificate
                    </button>
                    <button type="button" className={reviewMode === 'all' ? 'active' : ''} onClick={() => setReviewMode('all')}>
                      Tutte
                    </button>
                  </div>
                  <label>
                    Durata min
                    <input type="number" min="0" max="120" step="1" value={minDuration} onChange={(e) => setMinDuration(Number(e.target.value))} />
                  </label>
                  <label>
                    Conf. min
                    <input type="number" min="0" max="100" step="5" value={minConfidence} onChange={(e) => setMinConfidence(Number(e.target.value))} />
                  </label>
                  <span className="review-counter">
                    {filteredTracks.length} in lista · {reviewStats.reviewable} revisionabili · {reviewStats.total} totali
                  </span>
                </div>
                <div className="track-table">
                  {filteredTracks.slice(0, 80).map((track) => (
                    <div
                      key={track.id}
                      className={`track-row ${track.id === selectedTrackId ? 'active' : ''}`}
                      onClick={() => setSelectedTrackId(track.id)}
                    >
                      <button
                        className={`select-dot ${selectedTrackIds.has(track.id) ? 'checked' : ''}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleTrack(track.id);
                        }}
                        title="Seleziona per merge"
                      >
                        <Link2 size={13} />
                      </button>
                      <span className="track-id">ID #{track.track_id}</span>
                      <span>{track.player_name || 'Da identificare'}</span>
                      <span>{track.role || track.zone}</span>
                      <span>{fmt(track.duration_s, 's')}</span>
                      <span>{track.confidence}%</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="chart-panel">
                <div className="panel-heading compact">
                  <div>
                    <p className="eyebrow">Stabilita tracce</p>
                    <h3>Durata osservata</h3>
                  </div>
                </div>
                <div className="duration-chart" ref={durationChartRef}>
                  {durationChartSize.width > 1 && durationChartSize.height > 1 && (
                  <BarChart width={durationChartSize.width} height={durationChartSize.height} data={topTracks}>
                    <CartesianGrid stroke="rgba(255,255,255,.12)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: '#9ba8a0', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#9ba8a0', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#101815', border: '1px solid #294137', borderRadius: 8 }} />
                    <Bar dataKey="durata" radius={[6, 6, 0, 0]} fill="#d6ff5f" />
                  </BarChart>
                  )}
                </div>
              </div>
            </section>

            <section className="ai-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">OpenRouter</p>
                  <h3>Analisi AI del profilo</h3>
                </div>
                <Brain size={24} />
              </div>
              <div className="ai-controls">
                <select value={model} onChange={(e) => setModel(e.target.value)}>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>{m.name || m.id}</option>
                  ))}
                </select>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="OpenRouter API key opzionale"
                />
                <button className="primary-button" onClick={generateInsight} disabled={busy || !model}>
                  <Sparkles size={17} />
                  Genera insight {selectedProfileId ? 'profilo' : 'traccia'}
                </button>
              </div>
              <pre className="insight-box">{insight || 'Seleziona una traccia, correggi il profilo e genera un report scouting.'}</pre>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function TimelineReview({ detail, tracks, selectedTrackId, selectedTrackIds, activeWindow, videoTime, onSelectTrack, onToggleTrack, onSeek }) {
  const duration = Math.max(detail?.duration_s || 1, activeWindow?.end || 1, ...tracks.map((track) => track.last_time_s || 0));
  const windowStart = activeWindow ? Math.max(0, Math.min(100, (activeWindow.start / duration) * 100)) : 0;
  const windowWidth = activeWindow ? Math.max(0.8, ((Math.max(activeWindow.end, activeWindow.start + 0.1) - activeWindow.start) / duration) * 100) : 0;
  const playhead = Math.max(0, Math.min(100, (videoTime / duration) * 100));

  return (
    <section className="timeline-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Video review</p>
          <h3>Timeline tracce</h3>
        </div>
        <span>{activeWindow ? `${activeWindow.label}: ${fmt(activeWindow.start, 's')} - ${fmt(activeWindow.end, 's')}` : 'Seleziona una traccia per rivederla nel video'}</span>
      </div>

      <div className="timeline-ruler">
        <span>0s</span>
        <span>{fmt(duration / 2, 's')}</span>
        <span>{fmt(duration, 's')}</span>
        {activeWindow && <div className="active-window" style={{ left: `${windowStart}%`, width: `${windowWidth}%` }} />}
        <div className="playhead" style={{ left: `${playhead}%` }} />
      </div>

      <div className="timeline-list">
        {tracks.map((track) => {
          const left = Math.max(0, Math.min(100, ((track.first_time_s || 0) / duration) * 100));
          const width = Math.max(1.2, (((track.last_time_s || track.first_time_s || 0) - (track.first_time_s || 0)) / duration) * 100);
          const team = track.team_override || track.team;
          const selected = selectedTrackIds.has(track.id);
          return (
            <div key={track.id} className={`timeline-row ${track.id === selectedTrackId ? 'active' : ''}`}>
              <button
                type="button"
                className={`timeline-label ${selected ? 'checked' : ''}`}
                onClick={() => onToggleTrack(track.id)}
                title="Aggiungi o togli dal merge"
              >
                <span>#{track.track_id}</span>
                <small>{track.player_name || track.zone}</small>
              </button>
              <button
                type="button"
                className={`timeline-bar team-${team || 1}`}
                style={{ left: `${left}%`, width: `${width}%` }}
                onClick={() => {
                  onSelectTrack(track);
                  onSeek(track.first_time_s || 0, false);
                }}
                title={`Vai a #${track.track_id}`}
              >
                <span>{fmt(track.duration_s, 's')}</span>
              </button>
              <button type="button" className="seek-chip" onClick={() => onSeek(track.first_time_s || 0)}>
                <PlayCircle size={14} />
                {fmt(track.first_time_s, 's')}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Metric({ icon, label, value }) {
  return (
    <div className="metric-card">
      <div className="metric-icon">{React.cloneElement(icon, { size: 19 })}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PitchTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="pitch-tooltip">
      <b>#{item.track_id}</b>
      <span>{item.player_name || 'Da identificare'}</span>
      <small>{item.zone} · {item.confidence}%</small>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
