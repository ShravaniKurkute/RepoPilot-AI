import React, { useState, useMemo } from 'react'
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  ChevronRight,
  ChevronDown,
  Search,
  ChevronsRight,
  ChevronsDown,
} from 'lucide-react'
import type { TreeNode } from '../types'

interface DirectoryTreeProps {
  tree: TreeNode
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i] || 'B'}`
}

interface TreeNodeItemProps {
  node: TreeNode
  searchTerm: string
  expandedNodes: Set<string>
  toggleNode: (path: string) => void
  depth?: number
}

const TreeNodeItem: React.FC<TreeNodeItemProps> = ({
  node,
  searchTerm,
  expandedNodes,
  toggleNode,
  depth = 0,
}) => {
  const isDirectory = node.type === 'directory'
  const isExpanded = expandedNodes.has(node.path)

  const matchesSearch = useMemo(() => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()

    function checkNode(n: TreeNode): boolean {
      if (n.name.toLowerCase().includes(term)) return true
      if (n.children) {
        return n.children.some(checkNode)
      }
      return false
    }

    return checkNode(node)
  }, [node, searchTerm])

  if (!matchesSearch) return null

  return (
    <div className="text-xs select-none">
      <div
        onClick={() => isDirectory && toggleNode(node.path)}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        className={`flex items-center justify-between py-1.5 px-2 rounded-md transition cursor-pointer ${
          isDirectory
            ? 'hover:bg-slate-800/60 text-slate-200'
            : 'hover:bg-slate-800/40 text-slate-300'
        }`}
      >
        <div className="flex items-center space-x-1.5 overflow-hidden">
          {isDirectory ? (
            <span className="text-slate-500 hover:text-slate-300">
              {isExpanded ? (
                <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0" />
              )}
            </span>
          ) : (
            <span className="w-3.5" />
          )}

          {isDirectory ? (
            isExpanded ? (
              <FolderOpen className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
            ) : (
              <Folder className="h-3.5 w-3.5 text-cyan-500/80 shrink-0" />
            )
          ) : node.language ? (
            <FileCode className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          ) : (
            <FileText className="h-3.5 w-3.5 text-slate-400 shrink-0" />
          )}

          <span
            className={`truncate font-mono ${
              isDirectory ? 'font-semibold text-slate-200' : 'text-slate-300'
            } ${
              searchTerm && node.name.toLowerCase().includes(searchTerm.toLowerCase())
                ? 'bg-cyan-950 text-cyan-300 px-1 rounded border border-cyan-800/60'
                : ''
            }`}
          >
            {node.name}
          </span>
        </div>

        <div className="flex items-center space-x-2 shrink-0 ml-2">
          {node.language && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800 font-mono">
              {node.language}
            </span>
          )}
          {!isDirectory && node.size_bytes > 0 && (
            <span className="text-[11px] font-mono text-slate-500">
              {formatBytes(node.size_bytes)}
            </span>
          )}
        </div>
      </div>

      {isDirectory && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNodeItem
              key={child.path}
              node={child}
              searchTerm={searchTerm}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export const DirectoryTree: React.FC<DirectoryTreeProps> = ({ tree }) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(() => {
    // Expand root node by default
    return new Set<string>([tree.path])
  })

  const toggleNode = (path: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const expandAll = () => {
    const allPaths = new Set<string>()
    function collect(node: TreeNode) {
      if (node.type === 'directory') {
        allPaths.add(node.path)
        if (node.children) node.children.forEach(collect)
      }
    }
    collect(tree)
    setExpandedNodes(allPaths)
  }

  const collapseAll = () => {
    setExpandedNodes(new Set<string>([tree.path]))
  }

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col h-[520px]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Folder className="h-4 w-4 text-cyan-400" />
            Repository Directory Tree
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Explorable file hierarchy filtered with .gitignore rules
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={expandAll}
            className="px-2.5 py-1 text-[11px] rounded-lg bg-slate-950 border border-slate-800 text-slate-300 hover:text-cyan-400 flex items-center gap-1 transition cursor-pointer"
          >
            <ChevronsDown className="h-3 w-3" />
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="px-2.5 py-1 text-[11px] rounded-lg bg-slate-950 border border-slate-800 text-slate-300 hover:text-cyan-400 flex items-center gap-1 transition cursor-pointer"
          >
            <ChevronsRight className="h-3 w-3" />
            Collapse All
          </button>
        </div>
      </div>

      {/* Search Input */}
      <div className="mt-3 relative">
        <Search className="h-3.5 w-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          placeholder="Filter files or folders..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder:text-slate-600 text-xs focus:outline-none focus:border-cyan-500 transition font-mono"
        />
      </div>

      {/* Tree Content */}
      <div className="mt-3 flex-1 overflow-y-auto pr-1 space-y-0.5 border border-slate-800/60 rounded-xl p-2 bg-slate-950/40">
        <TreeNodeItem
          node={tree}
          searchTerm={searchTerm}
          expandedNodes={expandedNodes}
          toggleNode={toggleNode}
        />
      </div>
    </div>
  )
}

