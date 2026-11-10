"""Dependency detector and safe in-container package installation manager."""

from typing import List, Optional, Tuple
from app.core.logging import logger
from app.sandbox.container_manager import DockerSandboxContainer


class DependencyInstallResult:
    """Outcome of dependency installation inside container."""

    def __init__(
        self,
        attempted: bool,
        success: bool,
        manager: Optional[str] = None,
        stdout: str = "",
        stderr: str = "",
        error_message: Optional[str] = None,
    ):
        self.attempted = attempted
        self.success = success
        self.manager = manager
        self.stdout = stdout
        self.stderr = stderr
        self.error_message = error_message


class DependencyManager:
    """Detects and installs dependencies within isolated Docker containers."""

    async def detect_manifests(
        self,
        container: DockerSandboxContainer,
        workdir: str = "/workspace",
    ) -> List[str]:
        """Scans the container workspace for dependency manifest files."""
        res = await container.exec_command(["ls", "-1a", workdir], workdir=workdir)
        files = res.stdout.splitlines() if res.stdout else []
        manifests = []
        for f in files:
            name = f.strip()
            if name in ("requirements.txt", "pyproject.toml", "setup.py", "package.json", "package-lock.json"):
                manifests.append(name)
        return manifests

    async def install_dependencies_if_needed(
        self,
        container: DockerSandboxContainer,
        workdir: str = "/workspace",
        allow_network: bool = False,
        timeout_seconds: float = 60.0,
    ) -> DependencyInstallResult:
        """Installs dependencies inside container according to security policy."""
        manifests = await self.detect_manifests(container, workdir)
        if not manifests:
            logger.info("[DependencyManager] No dependency manifests detected in %s", container.short_id)
            return DependencyInstallResult(attempted=False, success=True, manager=None)

        # Python dependencies
        if "requirements.txt" in manifests or "pyproject.toml" in manifests:
            manager = "pip"
            if not allow_network:
                logger.info(
                    "[DependencyManager] Network isolation active (network_mode=none); skipping remote pip install."
                )
                return DependencyInstallResult(
                    attempted=False,
                    success=True,
                    manager="pip (offline/pre-installed)",
                )

            logger.info("[DependencyManager] Installing Python dependencies via pip inside %s...", container.short_id)
            if "requirements.txt" in manifests:
                cmd = ["pip", "install", "--no-cache-dir", "-r", "requirements.txt"]
            else:
                cmd = ["pip", "install", "--no-cache-dir", "."]

            res = await container.exec_command(cmd, workdir=workdir, timeout=timeout_seconds)
            if res.exit_code != 0:
                err = res.stderr.strip() or f"pip install exited with code {res.exit_code}"
                return DependencyInstallResult(
                    attempted=True,
                    success=False,
                    manager=manager,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    error_message=err,
                )
            return DependencyInstallResult(
                attempted=True,
                success=True,
                manager=manager,
                stdout=res.stdout,
                stderr=res.stderr,
            )

        # Node / JS dependencies
        if "package.json" in manifests:
            manager = "npm"
            if not allow_network:
                logger.info(
                    "[DependencyManager] Network isolation active; skipping remote npm install."
                )
                return DependencyInstallResult(
                    attempted=False,
                    success=True,
                    manager="npm (offline/pre-installed)",
                )

            logger.info("[DependencyManager] Installing Node dependencies with --ignore-scripts inside %s...", container.short_id)
            # Use --ignore-scripts to forbid arbitrary lifecycle execution
            cmd = ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"]
            res = await container.exec_command(cmd, workdir=workdir, timeout=timeout_seconds)
            if res.exit_code != 0:
                err = res.stderr.strip() or f"npm install exited with code {res.exit_code}"
                return DependencyInstallResult(
                    attempted=True,
                    success=False,
                    manager=manager,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    error_message=err,
                )
            return DependencyInstallResult(
                attempted=True,
                success=True,
                manager=manager,
                stdout=res.stdout,
                stderr=res.stderr,
            )

        return DependencyInstallResult(attempted=False, success=True, manager=None)


dependency_manager = DependencyManager()

