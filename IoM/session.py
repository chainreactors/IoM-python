"""
Malice Network Session Management

Provides session-aware wrappers around the MaliceClient for easier session-specific operations.
Sessions maintain context and provide direct command execution with automatic session_id metadata injection.
"""

import logging
from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING, Callable, Awaitable
from pathlib import Path
import grpclib.metadata

if TYPE_CHECKING:
    from .client import MaliceClient

from .exceptions import SessionError, TaskError
from .proto.clientpb import Session, Task, TaskRequest, SessionRequest
from .proto.modulepb import (
    Request, UploadRequest, DownloadRequest
)

logger = logging.getLogger(__name__)


class MaliceSession:
    """
    Session-aware wrapper that provides direct command execution capabilities.

    This class maintains session context and provides convenient methods for
    executing commands on specific implant sessions with automatic session_id
    metadata injection for all API calls.
    """

    def __init__(self, client: "MaliceClient", session_id: str):
        """Initialize with a connected client and session ID."""
        self.client = client
        self.session_id = session_id
        self._session_info: Optional[Session] = None

    def _create_session_request(self, **kwargs) -> SessionRequest:
        """Create SessionRequest with this session's ID."""
        return SessionRequest(session_id=self.session_id, **kwargs)

    def _inject_session_metadata(self, **kwargs: Any) -> Dict[str, Any]:
        """Inject session_id into metadata for gRPC calls."""
        metadata: Dict[str, str] = kwargs.get('metadata', {}).copy()
        metadata['session_id'] = self.session_id
        kwargs['metadata'] = metadata
        return kwargs

    async def refresh_info(self) -> Session:
        """Refresh and return current session information."""
        session_request = self._create_session_request()
        self._session_info = await self.client.get_session(session_request)
        assert self._session_info is not None, f"Session {self.session_id} not found"
        return self._session_info

    @property
    async def info(self) -> Session:
        """Get session information (cached with refresh option)."""
        if self._session_info is None:
            await self.refresh_info()
        assert self._session_info is not None
        return self._session_info

    @property
    async def is_alive(self) -> bool:
        """Check if session is alive."""
        info = await self.info
        return info.is_alive

    @property
    async def name(self) -> str:
        """Get session name."""
        info = await self.info
        return info.name

    @property
    async def target(self) -> str:
        """Get session target."""
        info = await self.info
        return info.target

    @property
    async def workdir(self) -> str:
        """Get current working directory."""
        info = await self.info
        return info.workdir

    # Dynamic API forwarding with session metadata injection
    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        """
        Dynamically forward API calls to client with automatic session_id metadata injection.

        This enables transparent access to all session-related API methods while
        automatically injecting the session_id into metadata.
        """
        client_method: Callable[..., Awaitable[Any]] = getattr(self.client, name)

        async def session_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper that injects session_id metadata before calling client method."""
            # Inject session metadata for all calls
            kwargs = self._inject_session_metadata(**kwargs)
            return await client_method(*args, **kwargs)

        # Preserve method metadata
        session_wrapper.__name__ = f"session_{name}"
        session_wrapper.__doc__ = client_method.__doc__ or f"Session-aware {name}"

        return session_wrapper

    # Command Execution Methods
    async def execute(self, command: str, args: Optional[List[str]] = None, timeout: float = 30.0) -> Task:
        """
        Execute a command on the session.

        Args:
            command: Command to execute
            args: Command arguments
            timeout: Execution timeout

        Returns:
            Task object representing the execution
        """
        assert await self.is_alive, f"Session {self.session_id} is not alive"

        from .proto.modulepb import ExecRequest
        exec_request = ExecRequest(
            path=command,
            args=args or [],
            output=True
        )

        return await self.client.execute(
            exec_request,
            timeout=timeout,
            **self._inject_session_metadata()
        )

    async def shell(self, command: str, timeout: float = 30.0) -> Task:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Execution timeout

        Returns:
            Task object representing the execution
        """
        info = await self.info
        is_windows = "windows" in info.os.name.lower()
        shell_cmd = "cmd" if is_windows else "sh"
        shell_arg = "/c" if is_windows else "-c"

        return await self.execute(shell_cmd, [shell_arg, command], timeout)

    async def cd(self, path: str) -> Task:
        """
        Change working directory.

        Args:
            path: Directory path to change to

        Returns:
            Task from the cd command
        """
        cd_request = Request(args=[path])
        response = await self.client.cd(cd_request, **self._inject_session_metadata())
        # Refresh session info to get updated working directory
        await self.refresh_info()
        return response

    async def pwd(self) -> Task:
        """Get current working directory from session."""
        pwd_request = Request()
        return await self.client.pwd(pwd_request, **self._inject_session_metadata())

    async def ls(self, path: str = ".") -> Task:
        """
        List directory contents.

        Args:
            path: Directory path to list

        Returns:
            Directory listing task
        """
        ls_request = Request(args=[path])
        return await self.client.ls(ls_request, **self._inject_session_metadata())

    async def upload(self, local_path: Union[str, Path], remote_path: str) -> Task:
        """
        Upload file to session.

        Args:
            local_path: Local file path
            remote_path: Remote destination path

        Returns:
            Task object representing the upload
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        with open(local_path, 'rb') as f:
            content = f.read()

        upload_request = UploadRequest(
            path=remote_path,
            data=content
        )

        return await self.client.upload(upload_request, **self._inject_session_metadata())

    async def download(self, remote_path: str, local_path: Optional[Union[str, Path]] = None) -> Task:
        """
        Download file from session.

        Args:
            remote_path: Remote file path
            local_path: Optional local save path

        Returns:
            Task object representing the download
        """
        download_request = DownloadRequest(path=remote_path)
        task = await self.client.download(download_request, **self._inject_session_metadata())

        # If local_path provided, we can save the result later when task completes
        if local_path is not None:
            task._local_save_path = Path(local_path)

        return task

    # Task Management
    async def get_tasks(self) -> Any:
        """Get all tasks for this session."""
        task_request = TaskRequest(session_id=self.session_id)
        return await self.client.get_tasks(task_request)

    async def get_task_content(self, task: Task) -> Any:
        """Get task content/result."""
        return await self.client.get_task_content(task, **self._inject_session_metadata())

    async def wait_task_content(self, task: Task, timeout: float = 60.0) -> Any:
        """Wait for task content to be available."""
        return await self.client.wait_task_content(task, timeout=timeout, **self._inject_session_metadata())

    async def wait_task_finish(self, task: Task, timeout: float = 60.0) -> Any:
        """Wait for task completion."""
        return await self.client.wait_task_finish(task, timeout=timeout, **self._inject_session_metadata())

    async def cancel_task(self, task_id: int) -> bool:
        """Cancel a running task."""
        try:
            from .proto.modulepb import TaskCtrl
            task_ctrl = TaskCtrl(task_id=task_id)
            await self.client.cancel_task(task_ctrl, **self._inject_session_metadata())
            return True
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False

    # Utility Methods
    def __str__(self) -> str:
        return f"MaliceSession(id={self.session_id[:8]}...)"

    def __repr__(self) -> str:
        return f"MaliceSession(session_id='{self.session_id}')"


class SessionManager:
    """
    High-level session management for MaliceClient.

    Provides convenient access to sessions and session-specific operations
    while maintaining the thin wrapper philosophy around the core client.
    """

    def __init__(self, client: "MaliceClient"):
        """Initialize with connected client."""
        self.client = client
        self._sessions_cache: Dict[str, MaliceSession] = {}

    async def list_sessions(self, alive_only: bool = False) -> Dict[str, Session]:
        """List all sessions or only alive ones."""
        session_request = SessionRequest(all=not alive_only)
        sessions_response = await self.client.get_sessions(session_request)

        # Convert sessions list to dict - type-safe access
        sessions_dict: Dict[str, Session] = {}
        for session in sessions_response.sessions:
            if not alive_only or session.is_alive:
                sessions_dict[session.session_id] = session

        return sessions_dict

    async def get_session(self, session_id: str) -> Optional[MaliceSession]:
        """
        Get MaliceSession wrapper for session ID.

        Args:
            session_id: Session ID or partial ID (will match prefix)

        Returns:
            MaliceSession wrapper or None if not found
        """
        # Check if full session ID provided
        if session_id in self._sessions_cache:
            return self._sessions_cache[session_id]

        # Get all sessions to find match
        sessions = await self.list_sessions(alive_only=False)

        # Exact match first
        if session_id in sessions:
            session_wrapper = MaliceSession(self.client, session_id)
            self._sessions_cache[session_id] = session_wrapper
            return session_wrapper

        # Prefix match
        matches = [sid for sid in sessions.keys() if sid.startswith(session_id)]
        if len(matches) == 1:
            matched_session_id = matches[0]
            session_wrapper = MaliceSession(self.client, matched_session_id)
            self._sessions_cache[matched_session_id] = session_wrapper
            return session_wrapper
        elif len(matches) > 1:
            raise SessionError(f"Ambiguous session ID '{session_id}': matches {matches}")

        return None

    async def get_session_by_name(self, name: str) -> Optional[MaliceSession]:
        """Get session by name."""
        sessions = await self.list_sessions(alive_only=False)
        for session_id, session_info in sessions.items():
            if session_info.name == name:
                cached_session = self._sessions_cache.get(session_id)
                if cached_session is None:
                    cached_session = MaliceSession(self.client, session_id)
                    self._sessions_cache[session_id] = cached_session
                return cached_session
        return None

    async def get_alive_sessions(self) -> List[MaliceSession]:
        """Get all alive sessions as MaliceSession wrappers."""
        alive = await self.list_sessions(alive_only=True)
        sessions: List[MaliceSession] = []
        for session_id in alive.keys():
            cached_session = self._sessions_cache.get(session_id)
            if cached_session is None:
                cached_session = MaliceSession(self.client, session_id)
                self._sessions_cache[session_id] = cached_session
            sessions.append(cached_session)
        return sessions

    async def interactive_session(self) -> Optional[MaliceSession]:
        """Get the first alive session for interactive use."""
        alive_sessions = await self.get_alive_sessions()
        return alive_sessions[0] if alive_sessions else None

    def clear_cache(self):
        """Clear the session cache."""
        self._sessions_cache.clear()