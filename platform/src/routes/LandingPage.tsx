/**
 * Solyra public landing page — spec:
 * docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md
 * The site's DEFAULT page: served publicly at `/` in every auth mode.
 * The app lives at /dashboard behind AuthGate. Must not require auth
 * or Firebase.
 */
import '@/components/landing/landing.css';
import { LandingNav } from '@/components/landing/LandingNav';
import { Hero } from '@/components/landing/Hero';

export default function LandingPage() {
  return (
    <main className="solyra-landing" data-testid="landing-page">
      <LandingNav />
      <Hero />
    </main>
  );
}
