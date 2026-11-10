"""Docker container manager enforcing ephemeral lifecycle, security boundaries, and resource limits."""

import asyncio
import io
import tarfile
import time
from typing import Any, Dict, List, Optional, Tuple
import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

from app.core.config import settings
from app.core.logging import logger


class ContainerExecResult:
    """Captured result of an in-container command execution."""

    def __init__(self, exit_code: int, stdout: str, stderr: str, duration_seconds: float):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_seconds = duration_seconds

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0

    @property
    def combined_output(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(f"[STDERR]\n{self.stderr.strip()}")
        return "\n".join(parts)


def is_docker_available() -> bool:
    """Checks whether the Docker daemon is accessible."""
    try:
        client = docker.from_env()
        return bool(client.ping())
    except Exception:
        return False


def get_docker_client() -> docker.DockerClient:
    """Retrieves an active Docker SDK client or raises a clean descriptive error."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as e:
        logger.warning("[DockerManager] Docker daemon unreachable: %s", e)
        raise RuntimeError(
            f"Docker engine is not running or unreachable on this host: {e}. "
            "Sandbox execution requires Docker Desktop or an accessible Docker daemon. "
            "Untrusted repository code will never be executed on the host machine."
        ) from e


class DockerSandboxContainer:
    """Represents a live isolated ephemeral container instance."""

    def __init__(self, client: docker.DockerClient, container: Container, timeout_seconds: int = 60):
        self._client = client
        self._container = container
        self._timeout_seconds = timeout_seconds
        self.container_id = container.id
        self.short_id = container.short_id

    def put_tar_bytes(self, target_dir: str, tar_data: bytes) -> None:
        """Transfers archive bytes into container filesystem."""
        self._container.put_archive(path=target_dir, data=tar_data)

    async def exec_command(
        self,
        command: List[str] | str,
        workdir: str = "/workspace",
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> ContainerExecResult:
        """Executes a command inside the container under an async timeout budget."""
        effective_timeout = timeout or self._timeout_seconds
        t0 = time.time()

        def _run_sync() -> Tuple[int, bytes, bytes]:
            res = self._container.exec_run(
                cmd=command,
                workdir=workdir,
                environment=environment or {},
                demux=True,
                privileged=False,
            )
            stdout_bytes = res.output[0] if res.output and res.output[0] else b""
            stderr_bytes = res.output[1] if res.output and len(res.output) > 1 and res.output[1] else b""
            return res.exit_code, stdout_bytes, stderr_bytes

        try:
            exit_code, stdout_b, stderr_b = await asyncio.wait_for(
                asyncio.to_thread(_run_sync),
                timeout=effective_timeout,
            )
            elapsed = time.time() - t0
            stdout_str = stdout_b.decode("utf-8", errors="replace")
            stderr_str = stderr_b.decode("utf-8", errors="replace")
            return ContainerExecResult(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_seconds=elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - t0
            logger.error(
                "[DockerSandbox] Command '%s' timed out after %.2fs inside container %s",
                command,
                elapsed,
                self.short_id,
            )
            return ContainerExecResult(
                exit_code=124,  # Standard timeout exit code
                stdout="",
                stderr=f"Command timed out after {effective_timeout}s.",
                duration_seconds=elapsed,
            )

    def cleanup(self) -> None:
        """Forcefully stops and removes the container."""
        try:
            logger.info("[DockerSandbox] Cleaning up container %s...", self.short_id)
            self._container.stop(timeout=1)
        except Exception:
            pass
        try:
            self._container.remove(force=True, v=True)
            logger.info("[DockerSandbox] Container %s removed.", self.short_id)
        except Exception as e:
            logger.debug("[DockerSandbox] Container %s removal note: %s", self.short_id, e)


class DockerContainerManager:
    """Factory creating and managing isolated ephemeral containers."""

    def __init__(self, client: Optional[docker.DockerClient] = None):
        self._client = client

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = get_docker_client()
        return self._client

    def resolve_image_for_language(self, language: str) -> str:
        """Selects language-specific base container image."""
        lang = language.lower().strip()
        if lang in ("javascript", "typescript", "node", "js", "ts"):
            return settings.DOCKER_NODE_IMAGE
        return settings.DOCKER_PYTHON_IMAGE

    async def spawn_container(
        self,
        language: str = "python",
        network_enabled: bool = False,
        timeout_seconds: Optional[int] = None,
    ) -> DockerSandboxContainer:
        """Creates and starts an ephemeral container with strict resource limits and security options."""
        client = self._get_client()
        image_name = self.resolve_image_for_language(language)
        effective_timeout = timeout_seconds or settings.DOCKER_SANDBOX_TIMEOUT_SECONDS

        # Pull image if not locally present
        try:
            await asyncio.to_thread(client.images.get, image_name)
        except (NotFound, ImageNotFound, APIError):
            logger.info("[DockerManager] Image '%s' not present locally. Pulling...", image_name)
            try:
                await asyncio.to_thread(client.images.pull, image_name)
            except Exception as pull_err:
                logger.warning("[DockerManager] Failed to pull image '%s': %s", image_name, pull_err)

        # Resource configuration
        mem_limit = f"{settings.DOCKER_MAX_MEMORY_MB}m"
        nano_cpus = int(settings.DOCKER_MAX_CPUS * 1e9)
        network_mode = "bridge" if network_enabled else settings.DOCKER_NETWORK_MODE

        logger.info(
            "[DockerManager] Spawning container (image: %s, net: %s, mem: %s, cpus: %.1f)...",
            image_name,
            network_mode,
            mem_limit,
            settings.DOCKER_MAX_CPUS,
        )

        def _create_container() -> Container:
            return client.containers.run(
                image=image_name,
                command="tail -f /dev/null",
                detach=True,
                network_mode=network_mode,
                mem_limit=mem_limit,
                memswap_limit=mem_limit,
                nano_cpus=nano_cpus,
                pids_limit=100,
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                working_dir="/workspace",
                labels={"repopilot": "sandbox_execution", "created_by": "repopilot_phase6"},
            )

        raw_container = await asyncio.to_thread(_create_container)
        sandbox = DockerSandboxContainer(
            client=client,
            container=raw_container,
            timeout_seconds=effective_timeout,
        )
        logger.info("[DockerManager] Spawned container %s (%s).", sandbox.short_id, image_name)

        # Create workspace directory inside container
        await sandbox.exec_command(["mkdir", "-p", "/workspace"])
        return sandbox


# Global singleton manager
container_manager = DockerContainerManager()
