export const lookupKey = "skycalm-pending-lookup";
type Draft = {
  number: string;
  date: string;
  schedule?: boolean;
  fromLanding?: boolean;
  until: number;
};
export function pendingLookup(): Draft | null {
  try {
    const d = JSON.parse(sessionStorage.getItem(lookupKey) || "null");
    return d &&
      d.until > Date.now() &&
      typeof d.number === "string" &&
      typeof d.date === "string"
      ? d
      : null;
  } catch {
    return null;
  }
}
export function startLookup(number: string, date: string) {
  sessionStorage.setItem(
    lookupKey,
    JSON.stringify({
      number,
      date,
      fromLanding: true,
      until: Date.now() + 600000,
    }),
  );
}
