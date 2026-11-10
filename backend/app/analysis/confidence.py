"""Validation and deduplication engine ensuring finding veracity and line accuracy."""

import re
from typing import List, Tuple
from app.analysis.schemas import CodeIssue
from app.core.config import settings


class ConfidenceValidator:
    """Validates evidence veracity, bounds line numbers, and deduplicates findings."""

    def __init__(self, min_confidence: float = settings.ANALYSIS_MIN_CONFIDENCE):
        self.min_confidence = min_confidence

    def validate_and_filter(
        self, issues: List[CodeIssue], source_code: str
    ) -> List[CodeIssue]:
        """Filters out invalid line ranges, hallucinated evidence, or low-confidence findings."""
        source_lines = source_code.splitlines()
        total_lines = len(source_lines)
        validated: List[CodeIssue] = []

        for issue in issues:
            # 1. Confidence threshold check
            if issue.confidence_score < self.min_confidence:
                continue

            # 2. Line number boundary checks
            start = max(1, issue.start_line)
            end = min(total_lines, max(start, issue.end_line))

            # 3. Evidence check against source code
            evidence_clean = issue.evidence.strip()
            if not evidence_clean:
                # Synthesize fallback evidence from actual line range if missing
                actual_slice = "\n".join(source_lines[start - 1 : end]).strip()
                if actual_slice:
                    issue = issue.model_copy(
                        update={"evidence": actual_slice, "start_line": start, "end_line": end}
                    )
                else:
                    continue
            else:
                # Evidence sanity check
                first_ev_line = evidence_clean.splitlines()[0].strip()
                if first_ev_line and first_ev_line not in source_code:
                    # Minor confidence penalty if evidence line doesn't match verbatim
                    new_conf = round(max(0.1, issue.confidence_score - 0.2), 2)
                    if new_conf < self.min_confidence:
                        continue
                    issue = issue.model_copy(
                        update={"confidence_score": new_conf, "start_line": start, "end_line": end}
                    )
                else:
                    issue = issue.model_copy(
                        update={"start_line": start, "end_line": end}
                    )

            validated.append(issue)

        return self.deduplicate(validated)

    def deduplicate(self, issues: List[CodeIssue]) -> List[CodeIssue]:
        """Eliminates duplicate issues targeting identical file locations and categories."""
        seen = {}
        for issue in issues:
            # Deduplication key: file_path + category + line range + subcategory/title
            key = (
                issue.file_path,
                issue.category,
                issue.start_line,
                issue.end_line,
                issue.subcategory or issue.issue_title.lower(),
            )

            if key not in seen:
                seen[key] = issue
            else:
                # Keep the finding with the higher confidence score
                if issue.confidence_score > seen[key].confidence_score:
                    seen[key] = issue

        return list(seen.values())


default_confidence_validator = ConfidenceValidator()

