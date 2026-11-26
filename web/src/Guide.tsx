import * as Dialog from "@radix-ui/react-dialog";
import { BookOpen, X } from "lucide-react";

export default function Guide() {
  return (
    <Dialog.Root>
      <Dialog.Trigger className="guide-button" aria-label="Forecast guide">
        <BookOpen size={16} />
        <span>
          <span className="guide-prefix">Forecast </span>guide
        </span>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="guide-dialog">
          <Dialog.Close className="close-guide" aria-label="Close guide">
            <X size={20} />
          </Dialog.Close>
          <Dialog.Title>Reading your forecast</Dialog.Title>
          <Dialog.Description>
            A weather model estimates how the air may feel along an approximate
            flight path.
          </Dialog.Description>
          <h3>The route</h3>
          <p>
            SkyCalm samples a great-circle path about every 25 km. It assumes
            800 km/h and cruise up to 35,000 ft, with about 150 km for climb and
            descent. Actual flights can follow a different path or altitude.
          </p>
          <h3>The colours</h3>
          <p>
            On a model-scored grid, LightGBM estimates a turbulence category at
            cruise levels. Select a point to see its model version, estimated
            probability and strongest contributing factor. With seven held-out
            aircraft reports, calibration remains uncertain. Grey marks missing
            data.
          </p>
          <p>
            Baseline grids use wind shear and deformation. Near the ground, both
            methods use surface CAPE as an indicator of convective conditions.
          </p>
          <h3>Seat comfort</h3>
          <p>
            Bumps can feel a little milder near the wings. The forecast
            describes the air along the route and applies to the whole aircraft.
          </p>
          <h3>Data time</h3>
          <p>
            The 36-hour window starts at the issue time of the NOAA GFS run.
            Replay pins a dated run so you can revisit the same forecast. The
            baseline provides categories without calibrated probabilities.
          </p>
          <p className="guide-disclaimer">
            For passenger education only. Do not use for navigation, flight
            planning or safety decisions.
          </p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
