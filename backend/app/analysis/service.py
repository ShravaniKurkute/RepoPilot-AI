"""Code analysis service orchestrating AST-guided context building, AI reasoning, and issue persistence."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.analyzer import BaseCodeAnalyzer, get_code_analyzer
from app.analysis.confidence import ConfidenceValidator, default_confidence_validator
from app.analysis.context_builder import AnalysisContextBuilder, default_context_builder
from app.analysis.issue_classifier import IssueClassifier, default_classifier
from app.analysis.schemas import (
    AnalysisRun,
    CodeIssue,
    IssueCategory,
    IssueListResponse,
    IssueSeverity,
    IssueStatus,
)
from app.code_analysis.service import code_analysis_service
from app.core.config import settings
from app.core.logging import logger
from app.database.models import CodeAnalysisRunModel, CodeIssueModel
from app.database.session import AsyncSessionLocal, check_database_connection
from app.rag.service import rag_service
from app.repository.file_walker import walk_repository


class BugDetectionService:
    """Manages AI code scans, issue validation, triage statuses, and persistence."""

    def __init__(
        self,
        analyzer: Optional[BaseCodeAnalyzer] = None,
        context_builder: Optional[AnalysisContextBuilder] = None,
        classifier: Optional[IssueClassifier] = None,
        validator: Optional[ConfidenceValidator] = None,
        storage_root: Optional[Path] = None,
    ):
        self.analyzer = analyzer or get_code_analyzer()
        self.context_builder = context_builder or default_context_builder
        self.classifier = classifier or default_classifier
        self.validator = validator or default_confidence_validator

        if storage_root is not None:
            self.storage_root = storage_root.resolve()
        else:
            p = Path(settings.WORKSPACE_STORAGE_PATH)
            self.storage_root = p if p.is_absolute() else (Path.cwd() / p).resolve()

        self._analysis_locks: Dict[str, asyncio.Lock] = {}

    def _get_analysis_lock(self, repo_id: str) -> asyncio.Lock:
        if repo_id not in self._analysis_locks:
            self._analysis_locks[repo_id] = asyncio.Lock()
        return self._analysis_locks[repo_id]

    def _get_repo_dir(self, repo_id: str) -> Path:
        return self.storage_root / repo_id

    def _get_issues_file(self, repo_id: str) -> Path:
        repo_dir = self._get_repo_dir(repo_id)
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir / "issues.json"

    def _get_runs_dir(self, repo_id: str) -> Path:
        runs_dir = self._get_repo_dir(repo_id) / "analysis_runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        return runs_dir

    # -------------------------------------------------------------
    # Local File Persistence Helpers
    # -------------------------------------------------------------
    def _load_local_issues(self, repo_id: str) -> List[CodeIssue]:
        issues_file = self._get_issues_file(repo_id)
        if not issues_file.exists():
            return []
        try:
            with open(issues_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [CodeIssue.model_validate(item) for item in data]
        except Exception as e:
            logger.error(f"Failed to read local issues for '{repo_id}': {e}")
            return []

    def _save_local_issues(self, repo_id: str, issues: List[CodeIssue]) -> None:
        issues_file = self._get_issues_file(repo_id)
        temp_file = issues_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump([i.model_dump() for i in issues], f, indent=2)
        temp_file.replace(issues_file)

    def _save_local_run(self, repo_id: str, run: AnalysisRun) -> None:
        run_file = self._get_runs_dir(repo_id) / f"{run.run_id}.json"
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(run.model_dump(), f, indent=2)

    def _load_latest_local_run(self, repo_id: str) -> Optional[AnalysisRun]:
        runs_dir = self._get_runs_dir(repo_id)
        run_files = sorted(list(runs_dir.glob("*.json")), key=lambda p: p.stat().st_mtime, reverse=True)
        if not run_files:
            return None
        try:
            with open(run_files[0], "r", encoding="utf-8") as f:
                return AnalysisRun.model_validate(json.load(f))
        except Exception:
            return None

    # -------------------------------------------------------------
    # Core Analysis Orchestration
    # -------------------------------------------------------------
    async def analyze_repository(
        self,
        repository_id: str,
        categories: Optional[List[IssueCategory]] = None,
    ) -> AnalysisRun:
        """Executes repository-wide AI code analysis across files and symbols."""
        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        lock = self._get_analysis_lock(repository_id)
        if lock.locked():
            logger.info("Analysis for repository '%s' is already in progress. Waiting on lock...", repository_id)

        async with lock:
            source_dir = repo_dir / "source"
            if not source_dir.exists():
                source_dir = repo_dir

            run_id = f"run_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc).isoformat()

            logger.info(f"Starting repository-wide AI analysis run '{run_id}' for '{repository_id}'...")

            # 1. Ensure Phase 2 AST analysis exists
            ast_analysis = code_analysis_service.get_analysis(repository_id)
            if not ast_analysis:
                try:
                    ast_analysis = code_analysis_service.analyze_repository(repository_id)
                except Exception as e:
                    logger.warning(f"AST extraction warning for '{repository_id}': {e}")
                    ast_analysis = None

            # 2. Collect repository files
            _, total_files, _, _, file_records = walk_repository(repo_root=source_dir)
            target_files = [rel_path.replace("\\", "/").strip("/") for rel_path, _ in file_records]

            run = AnalysisRun(
                run_id=run_id,
                repository_id=repository_id,
                status="running",
                current_stage="Discovering Files",
                stage_message=f"Discovered {len(target_files)} files. Inspecting repository context...",
                target_type="repository",
                target_path=None,
                total_files=len(target_files),
                analyzed_files=0,
                total_issues=0,
                started_at=now,
            )
            self._save_local_run(repository_id, run)

            # 3. Check and ensure RAG indexing is completed before running AI code analysis
            rag_stats = rag_service.get_indexing_status(repository_id)
            if rag_stats.total_chunks == 0 or rag_stats.status != "completed":
                logger.info(
                    "Repository '%s' RAG index not ready (chunks=%d, status=%s). Running indexing...",
                    repository_id,
                    rag_stats.total_chunks,
                    rag_stats.status,
                )

                async def _update_indexing_stage(stage: str, msg: str):
                    run.current_stage = stage
                    run.stage_message = msg
                    self._save_local_run(repository_id, run)

                try:
                    idx_res = await rag_service.index_repository(
                        repository_id, progress_callback=_update_indexing_stage
                    )
                    if idx_res.status == "failed":
                        run.status = "failed"
                        run.current_stage = "Analysis Failed"
                        run.stage_message = f"RAG indexing failed: {idx_res.error_message or 'Unknown error'}"
                        run.error_message = f"RAG indexing failed: {idx_res.error_message or 'Unknown error'}"
                        run.completed_at = datetime.now(timezone.utc).isoformat()
                        self._save_local_run(repository_id, run)
                        return run
                except Exception as rag_err:
                    logger.error(
                        "RAG indexing exception during repository analysis for '%s': %s",
                        repository_id,
                        rag_err,
                        exc_info=True,
                    )
                    run.status = "failed"
                    run.current_stage = "Analysis Failed"
                    run.stage_message = f"RAG indexing failed: {rag_err}"
                    run.error_message = f"RAG indexing failed: {rag_err}"
                    run.completed_at = datetime.now(timezone.utc).isoformat()
                    self._save_local_run(repository_id, run)
                    return run

            # Transition to Running AI Analysis stage
            run.current_stage = "Running AI Analysis"
            run.stage_message = f"Starting AI analysis across {len(target_files)} files..."
            self._save_local_run(repository_id, run)

            all_detected_issues: List[CodeIssue] = []
            timed_out_files: List[str] = []
            failed_files: List[str] = []
            processed_lock = asyncio.Lock()

            # 4. Analyze files in bounded concurrent batches
            concurrency = max(1, min(settings.ANALYSIS_MAX_CONCURRENCY, 4))
            semaphore = asyncio.Semaphore(concurrency)

            async def _analyze_file_task(rel_path: str) -> List[CodeIssue]:
                async with semaphore:
                    full_path = source_dir / rel_path
                    if not full_path.is_file():
                        async with processed_lock:
                            run.analyzed_files += 1
                            run.stage_message = f"Analyzed {run.analyzed_files} of {run.total_files} files..."
                            self._save_local_run(repository_id, run)
                        return []

                    try:
                        content = full_path.read_text(encoding="utf-8", errors="replace")
                    except Exception as read_err:
                        logger.warning("Failed to read file '%s': %s", rel_path, read_err)
                        async with processed_lock:
                            run.analyzed_files += 1
                            run.stage_message = f"Analyzed {run.analyzed_files} of {run.total_files} files..."
                            self._save_local_run(repository_id, run)
                        return []

                    file_ast = ast_analysis.files.get(rel_path) if ast_analysis else None
                    try:
                        file_issues = await self._analyze_file_content(
                            repository_id=repository_id,
                            run_id=run_id,
                            file_path=rel_path,
                            source_code=content,
                            file_analysis=file_ast,
                            categories=categories,
                        )
                        return file_issues
                    except Exception as file_err:
                        err_msg = str(file_err)
                        if "timed out" in err_msg.lower():
                            logger.error("AI code analysis timed out for '%s': %s", rel_path, err_msg)
                            timed_out_files.append(rel_path)
                        else:
                            logger.error("AI code analysis failed for '%s': %s", rel_path, err_msg)
                            failed_files.append(rel_path)
                        return []
                    finally:
                        async with processed_lock:
                            run.analyzed_files += 1
                            run.stage_message = f"Analyzed {run.analyzed_files} of {run.total_files} files..."
                            self._save_local_run(repository_id, run)

            tasks = [_analyze_file_task(p) for p in target_files]
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=False)
                for res in results:
                    all_detected_issues.extend(res)

            # 5. Finalize Run Statistics
            deduped = self.validator.deduplicate(all_detected_issues)
            run.total_issues = len(deduped)
            run.critical_count = sum(1 for i in deduped if i.severity == "Critical")
            run.high_count = sum(1 for i in deduped if i.severity == "High")
            run.medium_count = sum(1 for i in deduped if i.severity == "Medium")
            run.low_count = sum(1 for i in deduped if i.severity == "Low")
            run.informational_count = sum(1 for i in deduped if i.severity == "Informational")
            run.completed_at = datetime.now(timezone.utc).isoformat()

            timeout_sec = getattr(self.analyzer, "_timeout", settings.gemini_request_timeout)

            if timed_out_files and len(timed_out_files) == len(target_files) and len(target_files) > 0:
                run.status = "timed_out"
                run.current_stage = "Analysis Timed Out"
                run.error_message = (
                    f"Analysis timed out on all {len(timed_out_files)} files after {timeout_sec}s. "
                    "Consider scanning individual files or increasing GEMINI_REQUEST_TIMEOUT in backend/.env."
                )
                run.stage_message = run.error_message
            elif failed_files and len(failed_files) == len(target_files) and len(target_files) > 0:
                run.status = "failed"
                run.current_stage = "Analysis Failed"
                run.error_message = f"Analysis failed on files: {', '.join(failed_files[:3])}"
                run.stage_message = run.error_message
            else:
                run.status = "completed"
                run.current_stage = "Analysis Completed"
                if timed_out_files:
                    run.error_message = f"Completed with timeouts on {len(timed_out_files)} file(s): {', '.join(timed_out_files[:3])}"
                    run.stage_message = f"Completed with {len(deduped)} issues ({len(timed_out_files)} timeouts)."
                else:
                    run.stage_message = f"Completed analysis. Detected {len(deduped)} issues."

            # 6. Persist run and issues
            self._save_local_run(repository_id, run)
            self._save_local_issues(repository_id, deduped)
            await self._sync_to_postgres(repository_id, run, deduped)

            logger.info(
                f"AI analysis run '{run_id}' completed for '{repository_id}': status={run.status}, "
                f"{len(deduped)} total issues found ({run.critical_count} critical, {run.high_count} high)."
            )

            return run

    async def analyze_file(
        self,
        repository_id: str,
        file_path: str,
        categories: Optional[List[IssueCategory]] = None,
    ) -> AnalysisRun:
        """Executes targeted AI code analysis for a single source file."""
        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        norm_path = file_path.replace("\\", "/").strip("/")
        source_dir = repo_dir / "source"
        if not source_dir.exists():
            source_dir = repo_dir

        full_path = source_dir / norm_path
        if not full_path.is_file():
            raise ValueError(f"File '{file_path}' does not exist in repository.")

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        content = full_path.read_text(encoding="utf-8", errors="replace")

        ast_analysis = code_analysis_service.get_analysis(repository_id)
        file_ast = ast_analysis.files.get(norm_path) if ast_analysis else None

        run = AnalysisRun(
            run_id=run_id,
            repository_id=repository_id,
            status="running",
            current_stage="Running AI Analysis",
            stage_message=f"Analyzing file '{norm_path}'...",
            target_type="file",
            target_path=norm_path,
            total_files=1,
            analyzed_files=0,
            started_at=now,
        )
        self._save_local_run(repository_id, run)

        try:
            detected_issues = await self._analyze_file_content(
                repository_id=repository_id,
                run_id=run_id,
                file_path=norm_path,
                source_code=content,
                file_analysis=file_ast,
                categories=categories,
            )
        except Exception as file_err:
            err_msg = str(file_err)
            run.completed_at = datetime.now(timezone.utc).isoformat()
            if "timed out" in err_msg.lower():
                run.status = "timed_out"
                run.current_stage = "Analysis Timed Out"
                timeout_sec = getattr(self.analyzer, "_timeout", settings.gemini_request_timeout)
                run.error_message = (
                    f"File analysis timed out after {timeout_sec}s: {err_msg}"
                )
                run.stage_message = run.error_message
            else:
                run.status = "failed"
                run.current_stage = "Analysis Failed"
                run.error_message = (
                    self.analyzer._sanitize_error(err_msg)
                    if hasattr(self.analyzer, "_sanitize_error")
                    else err_msg
                )
                run.stage_message = run.error_message
            self._save_local_run(repository_id, run)
            raise file_err

        # Merge with existing repository issues
        existing_issues = self._load_local_issues(repository_id)
        # Remove old issues for this specific file
        retained = [i for i in existing_issues if i.file_path != norm_path]
        all_issues = self.validator.deduplicate(retained + detected_issues)

        run.analyzed_files = 1
        run.total_issues = len(detected_issues)
        run.critical_count = sum(1 for i in detected_issues if i.severity == "Critical")
        run.high_count = sum(1 for i in detected_issues if i.severity == "High")
        run.medium_count = sum(1 for i in detected_issues if i.severity == "Medium")
        run.low_count = sum(1 for i in detected_issues if i.severity == "Low")
        run.informational_count = sum(1 for i in detected_issues if i.severity == "Informational")
        run.status = "completed"
        run.current_stage = "Analysis Completed"
        run.stage_message = f"File '{norm_path}' analyzed: {len(detected_issues)} issues found."
        run.completed_at = datetime.now(timezone.utc).isoformat()

        self._save_local_run(repository_id, run)
        self._save_local_issues(repository_id, all_issues)
        await self._sync_to_postgres(repository_id, run, all_issues)

        return run

    async def analyze_function(
        self,
        repository_id: str,
        file_path: str,
        symbol_name: str,
    ) -> AnalysisRun:
        """Executes targeted AI analysis on an individual function, method, or class."""
        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        norm_path = file_path.replace("\\", "/").strip("/")
        source_dir = repo_dir / "source"
        if not source_dir.exists():
            source_dir = repo_dir

        full_path = source_dir / norm_path
        if not full_path.is_file():
            raise ValueError(f"File '{file_path}' does not exist in repository.")

        content = full_path.read_text(encoding="utf-8", errors="replace")
        ast_analysis = code_analysis_service.get_analysis(repository_id)
        file_ast = ast_analysis.files.get(norm_path) if ast_analysis else None

        target_sym = None
        if file_ast:
            for s in file_ast.symbols:
                if s.name == symbol_name:
                    target_sym = s
                    break

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        run = AnalysisRun(
            run_id=run_id,
            repository_id=repository_id,
            status="running",
            current_stage="Running AI Analysis",
            stage_message=f"Analyzing symbol '{symbol_name}' in '{norm_path}'...",
            target_type="symbol",
            target_path=f"{norm_path}::{symbol_name}",
            total_files=1,
            analyzed_files=0,
            started_at=now,
        )
        self._save_local_run(repository_id, run)

        detected_issues = []
        if target_sym:
            try:
                ctx = await self.context_builder.build_context_for_symbol(
                    repository_id=repository_id,
                    file_path=norm_path,
                    source_code=content,
                    symbol=target_sym,
                    file_analysis=file_ast,
                )
                raw_findings = await self.analyzer.analyze_context(ctx)
                detected_issues = self._process_raw_findings(
                    raw_findings=raw_findings,
                    repository_id=repository_id,
                    run_id=run_id,
                    file_path=norm_path,
                    language=target_sym.language,
                    source_code=content,
                    fallback_symbol=symbol_name,
                )
            except Exception as sym_err:
                err_msg = str(sym_err)
                run.completed_at = datetime.now(timezone.utc).isoformat()
                if "timed out" in err_msg.lower():
                    run.status = "timed_out"
                    run.current_stage = "Analysis Timed Out"
                    timeout_sec = getattr(self.analyzer, "_timeout", settings.gemini_request_timeout)
                    run.error_message = f"Symbol analysis timed out after {timeout_sec}s: {err_msg}"
                    run.stage_message = run.error_message
                else:
                    run.status = "failed"
                    run.current_stage = "Analysis Failed"
                    run.error_message = (
                        self.analyzer._sanitize_error(err_msg)
                        if hasattr(self.analyzer, "_sanitize_error")
                        else err_msg
                    )
                    run.stage_message = run.error_message
                self._save_local_run(repository_id, run)
                raise sym_err

        existing_issues = self._load_local_issues(repository_id)
        all_issues = self.validator.deduplicate(existing_issues + detected_issues)

        run.analyzed_files = 1
        run.total_issues = len(detected_issues)
        run.critical_count = sum(1 for i in detected_issues if i.severity == "Critical")
        run.high_count = sum(1 for i in detected_issues if i.severity == "High")
        run.medium_count = sum(1 for i in detected_issues if i.severity == "Medium")
        run.low_count = sum(1 for i in detected_issues if i.severity == "Low")
        run.informational_count = sum(1 for i in detected_issues if i.severity == "Informational")
        run.status = "completed"
        run.current_stage = "Analysis Completed"
        run.stage_message = f"Symbol '{symbol_name}' analyzed: {len(detected_issues)} issues found."
        run.completed_at = datetime.now(timezone.utc).isoformat()

        self._save_local_run(repository_id, run)
        self._save_local_issues(repository_id, all_issues)
        await self._sync_to_postgres(repository_id, run, all_issues)

        return run

    async def _analyze_file_content(
        self,
        repository_id: str,
        run_id: str,
        file_path: str,
        source_code: str,
        file_analysis: Optional[any],
        categories: Optional[List[IssueCategory]],
    ) -> List[CodeIssue]:
        """Runs context extraction, AI analyzer, and normalization for one file."""
        # Build context
        context = await self.context_builder.build_context_for_file(
            repository_id=repository_id,
            file_path=file_path,
            source_code=source_code,
            file_analysis=file_analysis,
        )

        raw_findings = await self.analyzer.analyze_context(context)
        return self._process_raw_findings(
            raw_findings=raw_findings,
            repository_id=repository_id,
            run_id=run_id,
            file_path=file_path,
            language=context.language,
            source_code=source_code,
            categories=categories,
        )

    def _process_raw_findings(
        self,
        raw_findings: List[Dict[str, any]],
        repository_id: str,
        run_id: str,
        file_path: str,
        language: str,
        source_code: str,
        fallback_symbol: Optional[str] = None,
        categories: Optional[List[IssueCategory]] = None,
    ) -> List[CodeIssue]:
        """Normalizes and validates raw dict findings from LLM into structured CodeIssue models."""
        processed: List[CodeIssue] = []

        for raw in raw_findings:
            title = str(raw.get("issue_title", "Code Quality Finding")).strip()
            desc = str(raw.get("issue_description", title)).strip()
            cat = str(raw.get("category", "logic_bug"))
            subcat = raw.get("subcategory")
            sev = str(raw.get("severity", "Medium"))

            norm_cat, norm_subcat, norm_sev, cwe = self.classifier.normalize_classification(
                category=cat,
                subcategory=subcat,
                severity=sev,
                issue_title=title,
            )

            # Apply category filter if requested
            if categories and norm_cat not in categories:
                continue

            try:
                start_l = int(raw.get("start_line", 1))
                end_l = int(raw.get("end_line", start_l))
            except (ValueError, TypeError):
                start_l, end_l = 1, 1

            try:
                conf = float(raw.get("confidence_score", 0.8))
                conf = max(0.0, min(1.0, conf))
            except (ValueError, TypeError):
                conf = 0.8

            evidence = str(raw.get("evidence", "")).strip()
            tech_exp = str(raw.get("technical_explanation", desc)).strip()
            impact = str(raw.get("potential_impact", "May cause unexpected behavior or vulnerability.")).strip()
            fix = str(raw.get("suggested_fix", "Review and refactor the code.")).strip()
            related = raw.get("related_files", [])
            sym = raw.get("affected_symbol") or fallback_symbol

            issue_id = f"issue::{repository_id}::{file_path}::{norm_subcat or 'defect'}::{start_l}"

            issue = CodeIssue(
                issue_id=issue_id,
                repository_id=repository_id,
                analysis_run_id=run_id,
                file_path=file_path,
                language=language,
                issue_title=title,
                issue_description=desc,
                category=norm_cat,
                subcategory=norm_subcat,
                severity=norm_sev,
                confidence_score=conf,
                start_line=start_l,
                end_line=end_l,
                affected_symbol=sym,
                evidence=evidence,
                technical_explanation=tech_exp,
                potential_impact=impact,
                suggested_fix=fix,
                related_files=related if isinstance(related, list) else [],
                cwe_id=cwe,
                detection_method="ast_rag_llm",
                status="Open",
            )
            processed.append(issue)

        return self.validator.validate_and_filter(processed, source_code)

    # -------------------------------------------------------------
    # Query & Status Management
    # -------------------------------------------------------------
    def get_run_status(
        self, repository_id: str, run_id: Optional[str] = None
    ) -> Optional[AnalysisRun]:
        """Retrieves analysis run details."""
        if run_id:
            run_file = self._get_runs_dir(repository_id) / f"{run_id}.json"
            if run_file.exists():
                try:
                    with open(run_file, "r", encoding="utf-8") as f:
                        return AnalysisRun.model_validate(json.load(f))
                except Exception:
                    pass
        return self._load_latest_local_run(repository_id)

    def get_issues(
        self,
        repository_id: str,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        file_path: Optional[str] = None,
        status: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> IssueListResponse:
        """Queries issues with filtering and aggregated category/severity breakdown."""
        all_issues = self._load_local_issues(repository_id)

        # Filter
        filtered = []
        for i in all_issues:
            if severity and i.severity.lower() != severity.lower():
                continue
            if category and i.category.lower() != category.lower():
                continue
            if status and i.status.lower() != status.lower():
                continue
            if file_path and file_path.lower() not in i.file_path.lower():
                continue
            if min_confidence is not None and i.confidence_score < min_confidence:
                continue
            filtered.append(i)

        # Breakdowns
        sev_counts: Dict[str, int] = {}
        cat_counts: Dict[str, int] = {}
        for i in filtered:
            sev_counts[i.severity] = sev_counts.get(i.severity, 0) + 1
            cat_counts[i.category] = cat_counts.get(i.category, 0) + 1

        return IssueListResponse(
            repository_id=repository_id,
            total_issues=len(filtered),
            severity_breakdown=sev_counts,
            category_breakdown=cat_counts,
            issues=filtered,
        )

    def get_issue(self, repository_id: str, issue_id: str) -> Optional[CodeIssue]:
        """Fetches a single issue by ID."""
        issues = self._load_local_issues(repository_id)
        for i in issues:
            if i.issue_id == issue_id:
                return i
        return None

    async def update_issue_status(
        self,
        issue_id: str,
        new_status: IssueStatus,
        notes: Optional[str] = None,
    ) -> Optional[CodeIssue]:
        """Updates triage status for an issue (Open, Confirmed, False Positive, Resolved, Ignored)."""
        # Find repository ID from issue_id format "issue::<repo_id>::<path>::..."
        parts = issue_id.split("::")
        if len(parts) >= 2:
            repository_id = parts[1]
        else:
            return None

        issues = self._load_local_issues(repository_id)
        updated_issue = None

        for idx, i in enumerate(issues):
            if i.issue_id == issue_id:
                updated_issue = i.model_copy(update={"status": new_status})
                issues[idx] = updated_issue
                break

        if updated_issue:
            self._save_local_issues(repository_id, issues)

            # Update PostgreSQL if active
            if await check_database_connection():
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            update(CodeIssueModel)
                            .where(CodeIssueModel.id == issue_id)
                            .values(status=new_status)
                        )
                        await session.commit()
                except Exception as e:
                    logger.warning(f"Could not update status in PostgreSQL: {e}")

        return updated_issue

    async def _sync_to_postgres(
        self,
        repository_id: str,
        run: AnalysisRun,
        issues: List[CodeIssue],
    ) -> None:
        """Synchronizes run and issue records to PostgreSQL database if reachable."""
        if not await check_database_connection():
            return

        try:
            async with AsyncSessionLocal() as session:
                # 1. Upsert AnalysisRunModel
                run_model = CodeAnalysisRunModel(
                    id=run.run_id,
                    repository_id=run.repository_id,
                    status=run.status,
                    target_type=run.target_type,
                    target_path=run.target_path,
                    total_files=run.total_files,
                    analyzed_files=run.analyzed_files,
                    total_issues=run.total_issues,
                    critical_count=run.critical_count,
                    high_count=run.high_count,
                    medium_count=run.medium_count,
                    low_count=run.low_count,
                    informational_count=run.informational_count,
                    error_message=run.error_message,
                )
                session.add(run_model)

                # 2. Clear old issues for this repository to prevent duplicates
                await session.execute(
                    delete(CodeIssueModel).where(CodeIssueModel.repository_id == repository_id)
                )

                # 3. Insert new issues
                for issue in issues:
                    issue_model = CodeIssueModel(
                        id=issue.issue_id,
                        analysis_run_id=issue.analysis_run_id,
                        repository_id=issue.repository_id,
                        file_path=issue.file_path,
                        language=issue.language,
                        issue_title=issue.issue_title,
                        issue_description=issue.issue_description,
                        category=issue.category,
                        subcategory=issue.subcategory,
                        severity=issue.severity,
                        confidence_score=issue.confidence_score,
                        start_line=issue.start_line,
                        end_line=issue.end_line,
                        affected_symbol=issue.affected_symbol,
                        evidence=issue.evidence,
                        technical_explanation=issue.technical_explanation,
                        potential_impact=issue.potential_impact,
                        suggested_fix=issue.suggested_fix,
                        related_files=issue.related_files,
                        cwe_id=issue.cwe_id,
                        detection_method=issue.detection_method,
                        status=issue.status,
                    )
                    session.add(issue_model)

                await session.commit()
                logger.info(f"Synchronized analysis run '{run.run_id}' with {len(issues)} issues to PostgreSQL.")
        except Exception as e:
            logger.warning(f"Failed to synchronize analysis run to PostgreSQL: {e}")


# Global default service instance
bug_detection_service = BugDetectionService()

