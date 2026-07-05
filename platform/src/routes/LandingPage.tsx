/**
 * Solyra public landing page — spec:
 * docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md
 * The site's DEFAULT page: served publicly at `/` in every auth mode.
 * The app lives at /dashboard behind AuthGate. Must not require auth
 * or Firebase.
 */
export default function LandingPage() {
  return (
    <main className="solyra-landing" data-testid="landing-page">
      <h1>Solyra</h1>
    </main>
  );
}
