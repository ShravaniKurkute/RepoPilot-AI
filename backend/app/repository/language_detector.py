"""Programming language detection and source code distribution analysis."""

import os
from typing import Dict, List, Optional, Tuple
from app.repository.schemas import LanguageDistribution

# Extension mapping to standardized language names
EXTENSION_MAP: Dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyw": "Python",
    # JavaScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    # TypeScript
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    # Java
    ".java": "Java",
    # C
    ".c": "C",
    ".h": "C",
    # C++
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # PHP
    ".php": "PHP",
    ".phtml": "PHP",
    # Ruby
    ".rb": "Ruby",
    # HTML
    ".html": "HTML",
    ".htm": "HTML",
    # CSS & Preprocessors
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    # Structured Data
    ".json": "JSON",
    # Documentation
    ".md": "Markdown",
    ".markdown": "Markdown",
    # Database
    ".sql": "SQL",
}


def detect_language_by_extension(file_path: str) -> Optional[str]:
    """Identifies the language for a given file path based on extension."""
    _, ext = os.path.splitext(file_path)
    if not ext:
        return None
    return EXTENSION_MAP.get(ext.lower())


def calculate_language_distribution(
    file_records: List[Tuple[str, int]],
) -> List[LanguageDistribution]:
    """Calculates language counts, byte volume, and percentages across files.

    Args:
        file_records: List of (relative_file_path, file_size_in_bytes)

    Returns:
        Sorted list of LanguageDistribution objects ordered by byte volume descending.
    """
    if not file_records:
        return []

    lang_stats: Dict[str, Dict[str, int]] = {}
    total_source_bytes = 0

    for path, size in file_records:
        lang = detect_language_by_extension(path)
        if not lang:
            continue

        if lang not in lang_stats:
            lang_stats[lang] = {"files": 0, "bytes": 0}

        lang_stats[lang]["files"] += 1
        lang_stats[lang]["bytes"] += size
        total_source_bytes += size

    distribution: List[LanguageDistribution] = []
    for lang_name, stats in lang_stats.items():
        percentage = (
            round((stats["bytes"] / total_source_bytes) * 100.0, 2)
            if total_source_bytes > 0
            else 0.0
        )
        distribution.append(
            LanguageDistribution(
                name=lang_name,
                file_count=stats["files"],
                byte_count=stats["bytes"],
                percentage=percentage,
            )
        )

    # Sort descending by byte volume, then alphabetically
    distribution.sort(key=lambda x: (-x.byte_count, x.name))
    return distribution
