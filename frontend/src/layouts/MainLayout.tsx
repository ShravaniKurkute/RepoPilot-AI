import React from 'react'
import { Header } from '../components/Header'
import type { HealthResponse } from '../types'

interface MainLayoutProps {
  health: HealthResponse | null
  loading: boolean
  children: React.ReactNode
}

export const MainLayout: React.FC<MainLayoutProps> = ({ health, loading, children }) => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Header health={health} loading={loading} />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-500">
        RepoPilot AI — Autonomous Multi-Agent Software Engineer • Built with React, FastAPI, LangGraph & Docker
      </footer>
    </div>
  )
}
