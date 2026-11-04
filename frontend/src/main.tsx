import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Link, NavLink, Outlet, RouterProvider } from 'react-router'
import { Toaster } from 'sonner'
import { api } from './api'
import { cn } from './components/ui'
import './index.css'
import { LibraryPage } from './pages/Library'
import { SettingsPage } from './pages/Settings'
import { StudioPage } from './pages/Studio'
import { VideoPage } from './pages/Video'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

/** A single frame of film: the mark. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="5" fill="#f8eee4" />
      {[5, 11, 17, 23].map((y) => (
        <g key={y} fill="#1a0910">
          <rect x="3.5" y={y} width="3" height="4" rx="1" />
          <rect x="25.5" y={y} width="3" height="4" rx="1" />
        </g>
      ))}
      <rect x="9" y="5" width="14" height="7" fill="#b9d3f0" />
      <rect x="9" y="12.5" width="14" height="7" fill="#f6bacb" />
      <rect x="9" y="20" width="14" height="7" fill="#f4e18b" />
    </svg>
  )
}

function Header() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 4000 })
  const queue = health.data?.queue
  const live = (queue?.running ?? 0) > 0
  const tab = ({ isActive }: { isActive: boolean }) =>
    cn(
      'relative px-1 py-2 text-[15px] transition-colors',
      isActive ? 'text-bone after:absolute after:inset-x-0 after:-bottom-[3px] after:h-[2px] after:rounded-full after:bg-rev-pink' : 'text-smoke hover:text-bone',
    )
  return (
    <header className="sticky top-0 z-30 border-b border-seam bg-night/70 backdrop-blur-xl">
      <div className="mx-auto flex h-[68px] max-w-[1480px] items-center gap-6 px-5 sm:gap-10 lg:px-10">
        <Link to="/" aria-label="shortstock home" className="flex items-center gap-3">
          <Mark className="h-8 w-8" />
          <span className="display hidden text-[32px] sm:inline">shortstock</span>
        </Link>
        <nav className="flex items-center gap-5 sm:gap-7">
          <NavLink to="/" end className={tab}>
            Write
          </NavLink>
          <NavLink to="/library" className={tab}>
            Library
          </NavLink>
          <NavLink to="/settings" className={tab}>
            Settings
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-6">
          {health.data && (
            <span className="hidden items-center gap-2.5 text-[14px] text-dust sm:flex">
              <span className={cn('h-2 w-2 rounded-full', live ? 'tally' : 'bg-go shadow-[0_0_10px_rgba(188,226,176,0.6)]')} />
              {live ? (queue!.queued > 0 ? `On air, ${queue!.queued} waiting` : 'On air') : 'Ready'}
            </span>
          )}
          <a
            href="https://github.com/T3-Venture-Labs-Limited/short-stock"
            target="_blank"
            rel="noreferrer"
            className="hidden text-[14px] text-smoke transition-colors hover:text-bone sm:inline"
          >
            GitHub ↗
          </a>
        </div>
      </div>
    </header>
  )
}

function Layout() {
  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-[1480px] px-6 py-10 lg:px-10">
        <Outlet />
      </main>
      <Toaster
        position="top-center"
        theme="dark"
        toastOptions={{ classNames: { toast: '!rounded-[16px] !font-sans !text-[15px] !bg-panel !border-seam-up !text-bone' } }}
      />
    </div>
  )
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <StudioPage /> },
      { path: '/library', element: <LibraryPage /> },
      { path: '/videos/:runId', element: <VideoPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
