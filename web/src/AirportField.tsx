import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Check, MapPin } from "lucide-react";
import { city, getJson } from "./types";
import type { Airport } from "./types";

interface Props {
  label: string;
  selected: Airport | null;
  onChange: (a: Airport) => void;
}
export default function AirportField({ label, selected, onChange }: Props) {
  const id = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Airport[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setItems([]);
    setPending(true);
    setError("");
    setIndex(0);
    const timer = setTimeout(() => {
      getJson<{ airports: Airport[] }>(
        "/api/airports",
        { q: query },
        controller.signal,
      )
        .then((v) => {
          if (!controller.signal.aborted) {
            setItems(v.airports);
            setPending(false);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setPending(false);
            setError("Airport search is unavailable.");
          }
        });
    }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const outside = (e: PointerEvent) => {
      if (!wrapper.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const pick = (a: Airport) => {
    onChange(a);
    setOpen(false);
    wrapper.current?.querySelector("button")?.focus();
  };
  return (
    <div
      className="airport-field"
      ref={wrapper}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <label id={id + "-label"}>{label}</label>
      <button
        type="button"
        className="airport-trigger"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => {
          setQuery("");
          setOpen(!open);
        }}
      >
        <MapPin size={17} />
        <span>{selected ? city(selected) : "Select airport"}</span>{" "}
        <b>{selected?.code}</b>
        <span className="sr-only"> {label}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="airport-menu">
          <input
            ref={input}
            role="combobox"
            aria-label={"Search " + label.toLowerCase()}
            aria-expanded={open}
            aria-controls={id + "-list"}
            aria-autocomplete="list"
            aria-activedescendant={items[index] ? id + index : undefined}
            placeholder="City, airport or code"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setOpen(false);
                wrapper.current?.querySelector("button")?.focus();
              }
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((i) =>
                  Math.max(
                    0,
                    Math.min(
                      items.length - 1,
                      i + (e.key === "ArrowDown" ? 1 : -1),
                    ),
                  ),
                );
              }
              if (e.key === "Enter") {
                e.preventDefault();
                if (items[index]) pick(items[index]);
              }
            }}
          />
          <ul role="listbox" id={id + "-list"} aria-labelledby={id + "-label"}>
            {items.map((a, i) => (
              <li
                key={a.code}
                role="option"
                id={id + i}
                aria-selected={index === i}
                className={index === i ? "active" : ""}
                onPointerDown={(e) => e.preventDefault()}
                onMouseEnter={() => setIndex(i)}
                onClick={() => pick(a)}
              >
                <strong>{a.code}</strong>
                <span>
                  {city(a)}
                  <small>{a.name}</small>
                </span>
                {a.code === selected?.code && <Check size={14} />}
              </li>
            ))}
          </ul>
          {!items.length && (
            <p role="status">
              {error || (pending ? "Searching…" : "No matching airports.")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
