import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { clock } from "./api";

export type LaneModel = {
  id: string;
  title: string;
  detail: string;
  url: string;
  empty?: string;
};

type PlayerProps = {
  lanes: LaneModel[];
  activeId: string;
  onActive: (id: string) => void;
  origin: number;
};

export function Player({ lanes, activeId, onActive, origin }: PlayerProps) {
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(0.9);
  const [syncId, setSyncId] = useState(0);
  const timeRef = useRef(0);
  const signature = lanes.map((lane) => `${lane.id}:${lane.url}`).join("|");

  useEffect(() => {
    timeRef.current = 0;
    setTime(0);
    setDuration(0);
    setPlaying(false);
  }, [signature]);

  useEffect(() => {
    setSyncId((value) => value + 1);
  }, [activeId]);

  function seekAll(next: number) {
    const value = Math.max(0, next);
    timeRef.current = value;
    setTime(value);
    setSyncId((current) => current + 1);
  }

  function toggle() {
    const active = lanes.find((lane) => lane.id === activeId);
    if (!active?.url) return;
    setPlaying((current) => !current);
  }

  const marks = rulerMarks(origin, duration);

  return (
    <section className="compare">
      <header className="compare-head">
        <h3>试听对比</h3>
        <span>{duration > 0 ? `${clock(origin)} – ${clock(origin + duration)}` : "同一段时间"}</span>
      </header>
      {marks.length > 0 ? (
        <div className="ruler" aria-hidden="true">
          {marks.map((mark) => (
            <span key={mark}>{mark}</span>
          ))}
        </div>
      ) : null}
      <div className="lanes">
        {lanes.map((lane) => (
          <Lane
            key={`${lane.id}:${lane.url}`}
            lane={lane}
            active={lane.id === activeId}
            playing={playing && lane.id === activeId}
            volume={volume}
            syncId={syncId}
            syncTime={time}
            onPick={() => onActive(lane.id)}
            onReady={(length) => {
              if (lane.id === activeId) setDuration(length);
            }}
            onSeek={(value) => {
              onActive(lane.id);
              seekAll(value);
            }}
            onProcess={(value, length) => {
              if (lane.id !== activeId) return;
              timeRef.current = value;
              setDuration(length);
              setTime(value);
            }}
            onFinish={() => setPlaying(false)}
          />
        ))}
      </div>
      <div className="transport">
        <div className="transport-buttons">
          <button className="icon-button" type="button" onClick={() => seekAll(time - 5)} aria-label="后退 5 秒">
            -5
          </button>
          <button className="play" type="button" onClick={toggle} aria-label={playing ? "暂停" : "播放"}>
            {playing ? "Ⅱ" : (
              <svg className="play-glyph" viewBox="0 0 12 14" width="12" height="14" aria-hidden="true">
                <path fill="currentColor" d="M3.5 1.15 11 7 3.5 12.85Z" />
              </svg>
            )}
          </button>
          <button className="icon-button" type="button" onClick={() => seekAll(time + 5)} aria-label="前进 5 秒">
            +5
          </button>
        </div>
        <div className="time">
          {clock(origin + time)} / {clock(origin + duration)}
        </div>
        <label className="volume">
          音量
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            style={{ ["--fill" as string]: `${Math.round(volume * 100)}%` }}
            onChange={(event) => setVolume(Number(event.target.value))}
          />
        </label>
      </div>
    </section>
  );
}

function Lane({
  lane,
  active,
  playing,
  volume,
  syncId,
  syncTime,
  onPick,
  onReady,
  onSeek,
  onProcess,
  onFinish,
}: {
  lane: LaneModel;
  active: boolean;
  playing: boolean;
  volume: number;
  syncId: number;
  syncTime: number;
  onPick: () => void;
  onReady: (duration: number) => void;
  onSeek: (time: number) => void;
  onProcess: (time: number, duration: number) => void;
  onFinish: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const waveRef = useRef<WaveSurfer | null>(null);
  const syncTimeRef = useRef(syncTime);
  const playingRef = useRef(playing);
  const handlers = useRef({ onReady, onSeek, onProcess, onFinish });
  syncTimeRef.current = syncTime;
  playingRef.current = playing && active;
  handlers.current = { onReady, onSeek, onProcess, onFinish };

  useEffect(() => {
    if (!host.current || !lane.url) return;
    const wave = WaveSurfer.create({
      container: host.current,
      height: 64,
      waveColor: "#c8c3ba",
      progressColor: "#44403c",
      cursorColor: "#1c1917",
      cursorWidth: 1,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      interact: true,
      url: lane.url,
    });
    waveRef.current = wave;
    const place = () => {
      const length = wave.getDuration();
      if (!length) return;
      const next = Math.min(Math.max(0, syncTimeRef.current), length);
      if (Math.abs(wave.getCurrentTime() - next) > 0.08) wave.setTime(next);
    };
    wave.on("ready", () => {
      place();
      handlers.current.onReady(wave.getDuration());
      if (playingRef.current) void wave.play();
    });
    wave.on("interaction", () => handlers.current.onSeek(wave.getCurrentTime()));
    wave.on("audioprocess", () => handlers.current.onProcess(wave.getCurrentTime(), wave.getDuration()));
    wave.on("finish", () => {
      handlers.current.onProcess(wave.getDuration(), wave.getDuration());
      handlers.current.onFinish();
    });
    return () => {
      waveRef.current = null;
      wave.destroy();
    };
  }, [lane.url]);

  useEffect(() => {
    const wave = waveRef.current;
    if (!wave || !syncId || !wave.getDuration()) return;
    const next = Math.min(Math.max(0, syncTimeRef.current), wave.getDuration());
    if (Math.abs(wave.getCurrentTime() - next) > 0.08) wave.setTime(next);
  }, [syncId]);

  useEffect(() => {
    const wave = waveRef.current;
    if (!wave) return;
    wave.setVolume(active ? volume : 0);
    if (!playing) {
      wave.pause();
      return;
    }
    const length = wave.getDuration();
    if (length && Math.abs(wave.getCurrentTime() - syncTimeRef.current) > 0.2) {
      wave.setTime(Math.min(syncTimeRef.current, length));
    }
    void wave.play();
  }, [active, playing, volume]);

  const label = lane.detail && lane.detail !== lane.title ? `${lane.title} · ${lane.detail}` : lane.title;

  return (
    <article className={active ? "lane active" : "lane"}>
      <header>
        <input type="radio" name="lane" checked={active} onChange={onPick} aria-label={lane.title} />
        <b>{label}</b>
      </header>
      {lane.url ? <div className="wave" ref={host} /> : <div className="empty-lane">{lane.empty || "还没有可播放的结果"}</div>}
    </article>
  );
}

function rulerMarks(origin: number, duration: number): string[] {
  if (duration <= 0) return [];
  const steps = duration < 8 ? 1 : duration >= 20 ? 6 : 4;
  const labels = Array.from({ length: steps + 1 }, (_, index) => formatMark(origin + (duration * index) / steps));
  return labels.filter((label, index) => labels.indexOf(label) === index);
}

function formatMark(seconds: number): string {
  if (seconds > 0 && seconds < 10) {
    const rounded = Math.round(seconds * 10) / 10;
    if (!Number.isInteger(rounded)) return `${rounded.toFixed(1)}s`;
  }
  return clock(seconds);
}
