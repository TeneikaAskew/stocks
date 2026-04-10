export function LoadingSpinner({ size = 24 }: { size?: number }) {
  return (
    <div className="flex items-center justify-center">
      <div
        className="animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent-blue)]"
        style={{ width: size, height: size }}
      />
    </div>
  );
}
