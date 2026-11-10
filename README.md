# 🚀 RepoPilot AI — Autonomous AI Software Engineer

> An autonomous AI-powered software engineering platform designed to ingest, analyze, plan, fix, and validate software repositories using multi-agent orchestration, pgvector RAG, and isolated Docker execution sandboxes.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg?logo=typescript)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v3-38B2AC.svg?logo=tailwind-css)](https://tailwindcss.com)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://langchain.com/langgraph)

---

## 📖 Architecture & Documentation

Comprehensive system and design documentation is available in the [`docs/`](docs/) directory:

- [**Project Overview**](docs/PROJECT_OVERVIEW.md) — Vision, core capabilities, target personas, and use cases.
- [**System Architecture**](docs/SYSTEM_ARCHITECTURE.md) — Monorepo design, micro-services layout, security & isolation boundaries.
- [**Database Design**](docs/DATABASE_DESIGN.md) — Relational schema + pgvector HNSW indexing and ER diagram.
- [**AI Agent Architecture**](docs/AI_AGENT_ARCHITECTURE.md) — LangGraph state graph, multi-agent roles, Gemini integration, and self-correction loop.
- [**Development Roadmap**](docs/DEVELOPMENT_ROADMAP.md) — Step-by-step phased execution plan from baseline to production.

---

## 🏗️ Repository Layout

```
RepoPilot AI/
├── backend/                  # FastAPI Python backend
│   ├── app/
│   │   ├── main.py           # Application entry point, CORS, lifespan
│   │   ├── api/              # REST & SSE endpoints (/api/v1)
│   │   ├── core/             # Configuration, logging, security
│   │   ├── schemas/          # Pydantic data schemas
│   │   ├── services/         # Domain service coordinators
│   │   ├── repository/       # ZIP / GitHub ingestion & file tree walking
│   │   ├── code_analysis/    # Tree-sitter & Python AST analyzers
│   │   ├── rag/              # pgvector retrieval & Gemini embeddings
│   │   ├── database/         # SQLAlchemy models & async engine
│   │   ├── agents/           # LangGraph multi-agent orchestration
│   │   ├── execution/        # Ephemeral Docker container runners
│   │   └── testing/          # Pytest runners & test output parsers
│   ├── tests/                # Backend unit and integration tests
│   ├── requirements.txt      # Python dependencies
│   ├── pyproject.toml        # Backend build configuration & tooling
│   └── .env.example          # Backend environment variables
├── frontend/                 # React + TypeScript + Vite frontend
│   ├── src/
│   │   ├── components/       # Reusable UI widgets & diff visualizers
│   │   ├── pages/            # Application pages (Dashboard, RepoView)
│   │   ├── hooks/            # Custom React hooks (SSE streaming, etc.)
│   │   ├── services/         # API clients (Axios / Fetch)
│   │   ├── types/            # TypeScript interfaces & API contracts
│   │   ├── layouts/          # Page layouts and navigational shells
│   │   ├── App.tsx           # Main application view
│   │   └── main.tsx          # React DOM root entry
│   ├── package.json          # Node dependencies and scripts
│   ├── vite.config.ts        # Vite build configuration
│   └── tailwind.config.js    # Tailwind styling configuration
├── docs/                     # System design & architecture documents
├── .gitignore                # Global git ignore configuration
├── .env.example              # Top-level environment template
└── README.md                 # Project documentation
```

---

## ⚡ Quick Start

### 1. Prerequisites
- **Python**: 3.11 or newer
- **Node.js**: 18.x or newer (Node 20+ recommended)
- **Docker**: (Required in Phase 6 for isolated test execution)
- **PostgreSQL 16 with pgvector**: (Required in Phase 3 for vector persistence)

---

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create a Python virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Start the FastAPI development server
uvicorn app.main:app --reload --port 8000
```

The backend API will be available at:
- API Root: `http://localhost:8000`
- Interactive Swagger Docs: `http://localhost:8000/docs`
- Health Probe: `http://localhost:8000/api/v1/health`

---

### 3. Frontend Setup

```bash
# In a new terminal, navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```

The frontend will be running at:
- Client UI: `http://localhost:5173`

---

## 🛡️ Security Guidelines

RepoPilot AI is designed to interact with external codebases. To protect the host machine:
- **Zero Host Execution Rule**: Arbitrary code or test commands are never run on the host OS.
- **Docker Sandboxing**: Execution is delegated to isolated containers with no network access, unprivileged users, and strict memory/CPU limits.

---

## 📄 License
This project is licensed under the MIT License.

