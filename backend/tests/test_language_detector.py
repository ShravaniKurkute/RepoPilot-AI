"""Unit tests for programming language detection and distribution calculation."""

from app.repository.language_detector import (
    calculate_language_distribution,
    detect_language_by_extension,
)


def test_detect_language_by_extension():
    """Verify standard extensions map to their respective languages."""
    assert detect_language_by_extension("src/main.py") == "Python"
    assert detect_language_by_extension("frontend/App.tsx") == "TypeScript"
    assert detect_language_by_extension("server/index.js") == "JavaScript"
    assert detect_language_by_extension("core/Main.java") == "Java"
    assert detect_language_by_extension("engine/render.cpp") == "C++"
    assert detect_language_by_extension("driver/io.c") == "C"
    assert detect_language_by_extension("cmd/service.go") == "Go"
    assert detect_language_by_extension("src/lib.rs") == "Rust"
    assert detect_language_by_extension("api/index.php") == "PHP"
    assert detect_language_by_extension("app/models.rb") == "Ruby"
    assert detect_language_by_extension("public/index.html") == "HTML"
    assert detect_language_by_extension("styles/app.css") == "CSS"
    assert detect_language_by_extension("config/data.json") == "JSON"
    assert detect_language_by_extension("docs/README.md") == "Markdown"
    assert detect_language_by_extension("db/schema.sql") == "SQL"


def test_detect_unknown_extension():
    """Verify unknown or missing extensions return None."""
    assert detect_language_by_extension("Dockerfile") is None
    assert detect_language_by_extension(".gitignore") is None
    assert detect_language_by_extension("binary.xyz123") is None


def test_calculate_language_distribution():
    """Verify language distributions compute correct file counts, bytes, and percentages."""
    records = [
        ("app/main.py", 600),       # 60% of code
        ("app/utils.py", 200),      # 20% of code
        ("frontend/App.tsx", 200),  # 20% of code
        ("unknown.bin", 5000),      # Should be ignored
    ]

    distribution = calculate_language_distribution(records)

    assert len(distribution) == 2
    # Sorted by bytes descending
    assert distribution[0].name == "Python"
    assert distribution[0].file_count == 2
    assert distribution[0].byte_count == 800
    assert distribution[0].percentage == 80.0

    assert distribution[1].name == "TypeScript"
    assert distribution[1].file_count == 1
    assert distribution[1].byte_count == 200
    assert distribution[1].percentage == 20.0
