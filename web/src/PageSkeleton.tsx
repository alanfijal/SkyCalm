export function Skeleton({ label }: { label: string }) {
  return (
    <div className="load-skeleton" role="status">
      <span className="sr-only">{label}</span>
      <i />
      <i />
      <i />
    </div>
  );
}
export function PageSkeleton({ label }: { label: string }) {
  return (
    <main className="shell loading-page">
      <Skeleton label={label} />
    </main>
  );
}
