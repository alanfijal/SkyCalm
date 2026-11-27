import * as Dialog from "@radix-ui/react-dialog";
import { ArrowUpRight, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import guide from "../../services/delivery/turbulence.json";
import { categoryColor } from "./theme";
import "./cabinGuide.css";

export { guide };
export type CabinLevel = keyof typeof guide.levels;
export const forecastLevels = [
  "smooth",
  "light",
  "moderate",
  "severe",
] as const;
export function knownLevel(value: string): value is CabinLevel {
  return Object.hasOwn(guide.levels, value);
}

type Point = { x: number; y: number };
type Explain = (level: CabinLevel, trigger: HTMLElement, point?: Point) => void;
const CabinContext = createContext<Explain | null>(null);
export function useCabinGuide(): Explain {
  const explain = useContext(CabinContext);
  if (!explain) throw Error("Cabin guide is missing");
  return explain;
}

function dot(level: CabinLevel) {
  return (
    <i
      aria-hidden="true"
      className="level-dot"
      data-level={level}
      style={{
        background: categoryColor(
          level === "unreported" ? "unavailable" : level,
        ),
      }}
    />
  );
}

export function LevelButton({
  level,
  children,
  marker = false,
}: {
  level: CabinLevel;
  children?: ReactNode;
  marker?: boolean;
}) {
  const explain = useCabinGuide();
  const label = guide.levels[level].label;
  return (
    <button
      type="button"
      className="level-link"
      aria-haspopup="dialog"
      aria-label={
        typeof children === "object"
          ? undefined
          : label + " · What does this feel like?"
      }
      onClick={(event) => explain(level, event.currentTarget)}
    >
      {marker && dot(level)}
      {children ?? label}
    </button>
  );
}

export function LevelText({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\b(smooth|light|moderate|severe|unavailable|unreported)\b/gi)
        .map((word, i) => {
          const level = word.toLowerCase();
          return knownLevel(level) ? (
            <LevelButton key={i} level={level}>
              {word}
            </LevelButton>
          ) : (
            word
          );
        })}
    </>
  );
}

export function CabinGuideProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<{
    level: CabinLevel;
    trigger: HTMLElement;
    x: number;
    edge: number;
    above: boolean;
  } | null>(null);
  const explain = useCallback<Explain>((level, trigger, position) => {
    const rect = trigger.getBoundingClientRect();
    const bottom = position?.y ?? rect.bottom;
    const top = position?.y ?? rect.top;
    const above = bottom > window.innerHeight / 2;
    setActive({
      level,
      trigger,
      x: position?.x ?? rect.left,
      edge: above ? window.innerHeight - top : bottom,
      above,
    });
  }, []);
  const copy = active && guide.levels[active.level];
  return (
    <CabinContext.Provider value={explain}>
      {children}
      <Dialog.Root
        open={Boolean(active)}
        onOpenChange={(open) => {
          if (!open) setActive(null);
        }}
      >
        {active && copy && (
          <Dialog.Portal>
            <Dialog.Overlay className="cabin-overlay" />
            <Dialog.Content
              className="cabin-popover"
              data-above={active.above}
              style={
                {
                  "--anchor-x": active.x + "px",
                  "--anchor-edge": active.edge + "px",
                } as CSSProperties
              }
              onCloseAutoFocus={(event) => {
                event.preventDefault();
                active.trigger.focus({ preventScroll: true });
              }}
            >
              <Dialog.Close
                className="close-guide"
                aria-label="Close explanation"
              >
                <X size={18} />
              </Dialog.Close>
              <Dialog.Title>
                {dot(active.level)}
                {copy.label}
                {forecastLevels.some((level) => level === active.level)
                  ? active.level === "smooth"
                    ? " air"
                    : " turbulence"
                  : ""}
              </Dialog.Title>
              <Dialog.Description>
                {copy.summary} {copy.detail}
              </Dialog.Description>
              <p className="seatbelt-note">{guide.seatbelt}</p>
              <a
                className="cabin-source"
                href={guide.source}
                target="_blank"
                rel="noopener noreferrer"
              >
                FAA turbulence guide{" "}
                <ArrowUpRight size={13} aria-hidden="true" />
              </a>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </Dialog.Root>
    </CabinContext.Provider>
  );
}

export function CabinGuideSection() {
  return (
    <section
      className="cabin-guide-section"
      aria-labelledby="cabin-levels-heading"
    >
      <h3 id="cabin-levels-heading">What does turbulence feel like?</h3>
      <dl>
        {forecastLevels.map((level) => (
          <div key={level}>
            <dt>
              {dot(level)}
              {guide.levels[level].label}
            </dt>
            <dd>
              {guide.levels[level].summary} {guide.levels[level].detail}
            </dd>
          </div>
        ))}
      </dl>
      <p className="seatbelt-note">
        <a
          href={guide.passengerSource}
          target="_blank"
          rel="noopener noreferrer"
        >
          {guide.seatbelt}
        </a>{" "}
        Follow your crew’s instructions.
      </p>
      <a
        className="cabin-source"
        href={guide.source}
        target="_blank"
        rel="noopener noreferrer"
      >
        FAA turbulence reporting criteria{" "}
        <ArrowUpRight size={13} aria-hidden="true" />
      </a>
    </section>
  );
}
