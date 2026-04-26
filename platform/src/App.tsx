import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { RouteErrorBoundary } from '@/components/shared/RouteErrorBoundary';

const DashboardPage = lazy(() => import('@/routes/DashboardPage'));
const LiveMarketPage = lazy(() => import('@/routes/LiveMarketPage'));
const ChartsPage = lazy(() => import('@/routes/ChartsPage'));
const OptionsFlowPage = lazy(() => import('@/routes/OptionsFlowPage'));
const PlaybookPage = lazy(() => import('@/routes/PlaybookPage'));
const ReportsPage = lazy(() => import('@/routes/ReportsPage'));
const SignalsPage = lazy(() => import('@/routes/SignalsPage'));
const JournalPage = lazy(() => import('@/routes/JournalPage'));
const InsightsPage = lazy(() => import('@/routes/InsightsPage'));
const CatalystsPage = lazy(() => import('@/routes/CatalystsPage'));
const AdminPage = lazy(() => import('@/routes/AdminPage'));
const HelpPage = lazy(() => import('@/routes/HelpPage'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center">
      <LoadingSpinner size={32} />
    </div>
  );
}

// Per-route errorElement isolates a single page's render crash from the
// AppShell — sidebar + header stay rendered, the bad page shows a card.
const errorElement = <RouteErrorBoundary />;

const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement,
    children: [
      { path: '/', errorElement, element: <Suspense fallback={<PageLoader />}><DashboardPage /></Suspense> },
      { path: '/live', errorElement, element: <Suspense fallback={<PageLoader />}><LiveMarketPage /></Suspense> },
      { path: '/charts', errorElement, element: <Suspense fallback={<PageLoader />}><ChartsPage /></Suspense> },
      { path: '/options', errorElement, element: <Suspense fallback={<PageLoader />}><OptionsFlowPage /></Suspense> },
      { path: '/playbook', errorElement, element: <Suspense fallback={<PageLoader />}><PlaybookPage /></Suspense> },
      { path: '/reports', errorElement, element: <Suspense fallback={<PageLoader />}><ReportsPage /></Suspense> },
      { path: '/signals', errorElement, element: <Suspense fallback={<PageLoader />}><SignalsPage /></Suspense> },
      { path: '/journal', errorElement, element: <Suspense fallback={<PageLoader />}><JournalPage /></Suspense> },
      { path: '/insights', errorElement, element: <Suspense fallback={<PageLoader />}><InsightsPage /></Suspense> },
      { path: '/catalysts', errorElement, element: <Suspense fallback={<PageLoader />}><CatalystsPage /></Suspense> },
      { path: '/admin', errorElement, element: <Suspense fallback={<PageLoader />}><AdminPage /></Suspense> },
      { path: '/help', errorElement, element: <Suspense fallback={<PageLoader />}><HelpPage /></Suspense> },
    ],
  },
]);

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

export default App;
