/** Brand mark — ascending dot-row + "Stocks" wordmark. */
export function Brand({ tag }: { tag?: string }) {
  return (
    <div className="brand-mark">
      <div className="dot-row">
        <i />
        <i />
        <i />
      </div>
      <span>Stocks</span>
      {tag && <small>{tag}</small>}
    </div>
  );
}
