import React, { useState, useRef } from 'react'
import { UploadCloud, GitBranch, FolderArchive, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import type { RepositoryDetail } from '../types'
import { uploadRepository, cloneRepository } from '../services/repository'

interface IngestionCardProps {
  onIngestionSuccess: (repo: RepositoryDetail) => void
}

export const IngestionCard: React.FC<IngestionCardProps> = ({ onIngestionSuccess }) => {
  const [activeTab, setActiveTab] = useState<'zip' | 'github'>('zip')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [githubUrl, setGithubUrl] = useState('')
  const [githubBranch, setGithubBranch] = useState('')
  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setError('Please select a valid .zip archive.')
      setSelectedFile(null)
      return
    }
    setError(null)
    setSelectedFile(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0])
    }
  }

  const handleZipUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) {
      setError('Please select a ZIP file to upload.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      setSuccess(null)
      setStatusMessage('Uploading and extracting ZIP archive safely...')

      const response = await uploadRepository(selectedFile)
      setSuccess(`Repository '${response.data.name}' ingested successfully!`)
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      onIngestionSuccess(response.data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'ZIP upload failed.')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  const handleGithubClone = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!githubUrl.trim()) {
      setError('Please provide a public GitHub repository URL.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      setSuccess(null)
      setStatusMessage('Cloning remote GitHub repository (shallow depth=1)...')

      const response = await cloneRepository(githubUrl.trim(), githubBranch.trim() || undefined)
      setSuccess(`Repository '${response.data.name}' cloned and ingested successfully!`)
      setGithubUrl('')
      setGithubBranch('')
      onIngestionSuccess(response.data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'GitHub clone failed.')
    } finally {
      setLoading(false)
      setStatusMessage('')
    }
  }

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex items-center justify-between pb-5 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-cyan-400" />
            Ingest Codebase
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Ingest an entire codebase via ZIP archive or public GitHub clone.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex rounded-lg bg-slate-950 p-1 border border-slate-800 text-xs">
          <button
            type="button"
            onClick={() => {
              setActiveTab('zip')
              setError(null)
              setSuccess(null)
            }}
            className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'zip'
                ? 'bg-cyan-500 text-slate-950 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FolderArchive className="h-3.5 w-3.5" />
            ZIP Upload
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('github')
              setError(null)
              setSuccess(null)
            }}
            className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'github'
                ? 'bg-cyan-500 text-slate-950 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <GitBranch className="h-3.5 w-3.5" />
            GitHub URL
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="mt-4 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-start gap-2.5">
          <AlertCircle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">{error}</div>
        </div>
      )}

      {success && (
        <div className="mt-4 p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-xs text-emerald-300 flex items-start gap-2.5">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">{success}</div>
        </div>
      )}

      {/* ZIP Upload Form */}
      {activeTab === 'zip' && (
        <form onSubmit={handleZipUpload} className="mt-5 space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition flex flex-col items-center justify-center ${
              isDragging
                ? 'border-cyan-400 bg-cyan-950/20'
                : selectedFile
                ? 'border-emerald-500/60 bg-emerald-950/10'
                : 'border-slate-800 hover:border-slate-700 bg-slate-950/40'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFileSelect(e.target.files[0])
                }
              }}
            />

            <FolderArchive
              className={`h-10 w-10 mb-3 ${
                selectedFile ? 'text-emerald-400' : 'text-slate-500'
              }`}
            />

            {selectedFile ? (
              <div>
                <p className="text-sm font-semibold text-emerald-300">{selectedFile.name}</p>
                <p className="text-xs text-slate-400 mt-1">
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for ingestion
                </p>
                <p className="text-[11px] text-cyan-400 mt-2 hover:underline">
                  Click to choose a different archive
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-slate-200">
                  Drag & drop repository ZIP archive here
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  or click to browse from your computer (max 50 MB)
                </p>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={!selectedFile || loading}
            className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-cyan-500/20"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{statusMessage || 'Processing...'}</span>
              </>
            ) : (
              <>
                <span>Ingest Archive</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </form>
      )}

      {/* GitHub Clone Form */}
      {activeTab === 'github' && (
        <form onSubmit={handleGithubClone} className="mt-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label htmlFor="github-url-input" className="block text-xs font-medium text-slate-400 mb-1.5">
                GitHub Repository HTTPS URL
              </label>
              <input
                id="github-url-input"
                type="url"
                required
                placeholder="https://github.com/owner/repository"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                disabled={loading}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 placeholder:text-slate-600 text-xs focus:outline-none focus:border-cyan-500 transition font-mono"
              />
            </div>

            <div>
              <label htmlFor="github-branch-input" className="block text-xs font-medium text-slate-400 mb-1.5">
                Branch / Tag (Optional)
              </label>
              <input
                id="github-branch-input"
                type="text"
                placeholder="e.g. main, dev"
                value={githubBranch}
                onChange={(e) => setGithubBranch(e.target.value)}
                disabled={loading}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 placeholder:text-slate-600 text-xs focus:outline-none focus:border-cyan-500 transition font-mono"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="text-[11px] text-slate-500 flex items-center gap-1.5">
              <span>Security rule: HTTPS public repositories only</span>
              <span>•</span>
              <span>Shallow depth=1</span>
            </div>

            <button
              type="submit"
              disabled={!githubUrl.trim() || loading}
              className="px-6 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 cursor-pointer shadow-lg shadow-cyan-500/20"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{statusMessage || 'Cloning...'}</span>
                </>
              ) : (
                <>
                  <GitBranch className="h-4 w-4" />
                  <span>Clone & Ingest</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

