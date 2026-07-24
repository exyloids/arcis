export default function HomePage() {
  return (
    <main className="shell">
      <p className="eyebrow">ARCIS · PERSONAL FINANCE</p>
      <h1>Know where your money goes.</h1>
      <p className="lede">
        A read-only workspace for consolidating accounts, reconciling statements,
        and understanding spending.
      </p>
      <div className="status" role="status">
        <span className="dot" aria-hidden="true" />
        Foundation scaffold is running
      </div>
    </main>
  );
}
