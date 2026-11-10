"""Unit tests for repository file walking, .gitignore support, and directory tree building."""

from pathlib import Path
from app.repository.file_walker import walk_repository


def test_file_walker_structure_and_counts(tmp_path: Path):
    """Verify file walker recursively indexes files and computes accurate counts."""
    # Create mock repo directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('test')")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Documentation")
    (tmp_path / "README.md").write_text("# Root Readme")

    tree, total_files, total_dirs, total_bytes, records = walk_repository(tmp_path)

    assert total_files == 4
    assert total_dirs >= 3  # root + src + docs
    assert len(records) == 4
    assert tree.type == "directory"
    assert tree.children is not None
    assert len(tree.children) > 0


def test_file_walker_respects_default_exclusions(tmp_path: Path):
    """Verify default build and cache directories (.git, node_modules, .venv) are ignored."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("app = 1")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.json").write_text("{}")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pip.exe").write_text("bin")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.pyc").write_text("bytecode")

    tree, total_files, _, _, records = walk_repository(tmp_path)

    paths = [p for p, _ in records]
    assert "src/app.py" in paths
    assert not any("node_modules" in p for p in paths)
    assert not any(".venv" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
    assert total_files == 1


def test_file_walker_respects_gitignore(tmp_path: Path):
    """Verify .gitignore patterns filter out matching files and directories."""
    (tmp_path / ".gitignore").write_text("*.log\nsecret/\nignored_file.txt\n")
    (tmp_path / "app.log").write_text("log content")
    (tmp_path / "ignored_file.txt").write_text("ignore me")
    (tmp_path / "valid.py").write_text("x = 1")
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "keys.json").write_text("{}")

    tree, total_files, _, _, records = walk_repository(tmp_path)

    paths = [p for p, _ in records]
    assert "valid.py" in paths
    assert not any(p.endswith(".log") for p in paths)
    assert "ignored_file.txt" not in paths
    assert not any("secret" in p for p in paths)
