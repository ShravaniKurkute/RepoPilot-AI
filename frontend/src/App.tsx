import { useHealth } from './hooks/useHealth'
import { MainLayout } from './layouts/MainLayout'
import { Dashboard } from './pages/Dashboard'

export function App() {
  const { data: health, loading, error, lastChecked, refetch } = useHealth(15000)

  return (
    <MainLayout health={health} loading={loading}>
      <Dashboard
        health={health}
        loading={loading}
        error={error}
        lastChecked={lastChecked}
        onRefresh={refetch}
      />
    </MainLayout>
  )
}

export default App
