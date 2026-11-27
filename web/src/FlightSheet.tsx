import { useRef, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export function FlightSheet({
  children,
  level,
}: {
  children: ReactNode;
  level: string;
}) {
  const [open, setOpen] = useState(false),
    button = useRef<HTMLButtonElement>(null),
    start = useRef<number | null>(null),
    dragged = useRef(false);
  return (
    <div className="sheet-host">
      <div
        className="flight-sheet"
        onKeyDown={(e) => {
          if (e.key === "Escape" && open && !e.defaultPrevented) {
            setOpen(false);
            button.current?.focus();
          }
        }}
      >
        <button
          type="button"
          className="sheet-handle"
          ref={button}
          aria-expanded={open}
          aria-controls="mobile-route-timeline"
          onPointerDown={(e) => {
            start.current = e.clientY;
            dragged.current = false;
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerCancel={() => {
            start.current = null;
          }}
          onPointerUp={(e) => {
            if (
              start.current !== null &&
              Math.abs(e.clientY - start.current) > 24
            ) {
              dragged.current = true;
              setOpen(e.clientY < start.current);
            }
            start.current = null;
          }}
          onClick={() => {
            if (!dragged.current) setOpen((v) => !v);
            dragged.current = false;
          }}
        >
          <span>Flight details</span>
          <small>{level} peak</small>
          {open ? <ChevronDown size={19} /> : <ChevronUp size={19} />}
        </button>
        <div
          id="mobile-route-timeline"
          className="sheet-content"
          hidden={!open}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
