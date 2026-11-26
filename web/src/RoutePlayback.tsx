import { useCallback, useEffect, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { clock, type Sample } from "./types";
import "./recordedFlight.css";

const speed = 120;

export function useRoutePlayback(
  samples: Sample[] | undefined,
  index: number,
  setIndex: (i: number) => void,
) {
  const [playing, setPlaying] = useState(false);
  const last = !!samples && index === samples.length - 1;
  const stop = useCallback(() => setPlaying(false), []);
  function select(i: number) {
    stop();
    setIndex(i);
  }
  function toggle() {
    if (last) setIndex(0);
    setPlaying(!playing);
  }
  useEffect(() => {
    if (!playing || !samples?.[index + 1]) return;
    const delay =
      (Date.parse(samples[index + 1].at) - Date.parse(samples[index].at)) /
      speed;
    const timer = window.setTimeout(() => {
      setIndex(index + 1);
      if (index + 1 === samples.length - 1) setPlaying(false);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [index, playing, samples, setIndex]);
  return { playing, last, stop, select, toggle };
}

export function PlaybackControls({
  playback,
  current,
  recorded,
}: {
  playback: ReturnType<typeof useRoutePlayback>;
  current: Sample;
  recorded: boolean;
}) {
  const { playing, last, toggle } = playback;
  const label = recorded ? "replay" : "forecast route";
  return (
    <div className="recording-controls">
      <button type="button" onClick={toggle}>
        {playing ? (
          <Pause size={16} />
        ) : last ? (
          <RotateCcw size={16} />
        ) : (
          <Play size={16} />
        )}
        {playing ? "Pause " + label : last ? "Play again" : "Play " + label}
      </button>
      <span className="recording-speed">
        {!recorded && "Estimated route · "}
        <span className="sr-only">Playback speed </span>
        {speed}×
      </span>
      <time dateTime={current.at}>{clock(current.at)} UTC</time>
      <span>{current.altitudeFt.toLocaleString("en-GB")} ft</span>
    </div>
  );
}
