import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/app-shell'
import DashboardPage from '@/pages/DashboardPage'
import HostsPage from '@/pages/HostsPage'
import TunnelsPage from '@/pages/TunnelsPage'
import MountsPage from '@/pages/MountsPage'
import MirrorPage from '@/pages/MirrorPage'
import AiProxyPage from '@/pages/AiProxyPage'
import SettingsPage from '@/pages/SettingsPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'hosts', element: <HostsPage /> },
      { path: 'tunnels', element: <TunnelsPage /> },
      { path: 'mounts', element: <MountsPage /> },
      { path: 'mirror', element: <MirrorPage /> },
      { path: 'ai-proxy', element: <AiProxyPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
])
