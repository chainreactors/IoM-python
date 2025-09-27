"""
Malice Network Async Client

Elegant async wrapper around the generated MaliceRpcStub that provides:
- Automatic connection management with mTLS
- Clean Pythonic API for server operations
- Proper error handling and logging

This is a thin, focused wrapper that leverages the generated proto code.
"""

import logging
import ssl
from typing import Dict, List, Optional, Union, AsyncContextManager, Any, Callable, Awaitable
from pathlib import Path
import grpclib.client
from contextlib import asynccontextmanager
import grpclib.metadata

from .config import ClientConfig
from .exceptions import MaliceError, ConnectionError, AuthenticationError
from .proto.clientrpc import MaliceRpcStub
from .proto.clientpb import (
    LoginReq, Client, Empty, Basic, Sessions, SessionRequest, Session,
    Listeners, Listener, Pipeline, Tasks, TaskRequest, Task, TaskContext
)

logger = logging.getLogger(__name__)


class MaliceClient:
    """
    Async Malice Network client - elegant wrapper around MaliceRpcStub.

    This client provides a clean, Pythonic interface to the Malice Network
    server while being a thin wrapper around the generated gRPC stub.
    """

    def __init__(self, config: ClientConfig):
        """Initialize the client with configuration."""
        self.config = config
        self._channel: Optional[grpclib.client.Channel] = None
        self._stub: Optional[MaliceRpcStub] = None
        self._client_info: Optional[Client] = None
        self._basic_info: Optional[Basic] = None
        self._connected = False
        self._authenticated = False
        self._session_manager: Optional["SessionManager"] = None

        # Management collections (similar to Go version)
        self._clients: List[Client] = []
        self._listeners: Dict[str, Listener] = {}
        self._pipelines: Dict[str, Pipeline] = {}
        self._sessions: Dict[str, Session] = {}
        self._active_target: Optional[str] = None

    @classmethod
    def from_config_file(cls, config_path: Union[str, Path]) -> "MaliceClient":
        """Create client from configuration file."""
        config = ClientConfig.from_auth_file(config_path)
        return cls(config)

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected and self._channel is not None

    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated with server."""
        return self._authenticated and self._client_info is not None

    @property
    def sessions(self) -> "SessionManager":
        """Access to session management."""
        if not self._session_manager:
            from .session import SessionManager
            self._session_manager = SessionManager(self)
        return self._session_manager

    @property
    def client_info(self) -> Optional[Client]:
        """Get client information."""
        return self._client_info

    @property
    def basic_info(self) -> Optional[Basic]:
        """Get basic server information."""
        return self._basic_info

    @property
    def active_target(self) -> Optional[str]:
        """Get current active target session ID."""
        return self._active_target

    @active_target.setter
    def active_target(self, session_id: Optional[str]) -> None:
        """Set active target session ID."""
        self._active_target = session_id

    @property
    def clients(self) -> List[Client]:
        """Get list of connected clients."""
        return self._clients.copy()

    @property
    def listeners(self) -> Dict[str, Listener]:
        """Get dictionary of listeners by ID."""
        return self._listeners.copy()

    @property
    def pipelines(self) -> Dict[str, Pipeline]:
        """Get dictionary of pipelines by name."""
        return self._pipelines.copy()

    @property
    def cached_sessions(self) -> Dict[str, Session]:
        """Get dictionary of cached sessions by session_id."""
        return self._sessions.copy()

    async def connect(self, timeout: float = 10.0) -> None:
        """
        Connect and authenticate with the Malice Network server.

        Args:
            timeout: Connection timeout in seconds

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        if self.is_connected:
            return

        try:
            import tempfile
            import os

            # Create temporary certificate files (grpclib needs file paths)
            with tempfile.TemporaryDirectory() as temp_dir:
                ca_file = os.path.join(temp_dir, "ca.pem")
                cert_file = os.path.join(temp_dir, "cert.pem")
                key_file = os.path.join(temp_dir, "key.pem")

                # Write certificates to temporary files
                with open(ca_file, 'w') as f:
                    f.write(self.config.ca_certificate)
                with open(cert_file, 'w') as f:
                    f.write(self.config.certificate)
                with open(key_file, 'w') as f:
                    f.write(self.config.private_key)

                # Create SSL context with client certificates
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                ssl_context.load_cert_chain(cert_file, key_file)

                # Create gRPC channel
                self._channel = grpclib.client.Channel(
                    host=self.config.host,
                    port=self.config.port,
                    ssl=ssl_context
                )

                # Create the stub
                self._stub = MaliceRpcStub(self._channel)

                # Authenticate immediately while certs are available
                await self._authenticate()

            # Mark as connected after successful authentication
            self._connected = True
            logger.info(f"Connected to {self.config.address()} as {self.config.operator}")

        except Exception as e:
            await self._cleanup()
            raise ConnectionError(f"Failed to connect to {self.config.address()}", details=str(e))

    async def _authenticate(self) -> None:
        """Authenticate with the server."""
        try:
            login_req = LoginReq(
                name=self.config.operator,
                host=self.config.host,
                port=self.config.port
            )

            self._client_info = await self._stub.login_client(login_req)
            self._authenticated = True

        except Exception as e:
            raise AuthenticationError("Authentication failed", details=str(e))

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up connections."""
        self._authenticated = False
        self._client_info = None
        self._connected = False

        if self._channel:
            self._channel.close()
            self._channel = None
        self._stub = None

    # Context manager support
    async def __aenter__(self) -> "MaliceClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    # Dynamic API forwarding to stub
    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        """
        Dynamically forward method calls to the underlying stub.

        This enables transparent access to all stub methods without
        manually implementing each one, while maintaining type safety
        through .pyi stub files.
        """
        # Type-safe assertions - these should never fail if used correctly
        assert self._stub is not None, f"Client not connected. Call connect() first before accessing '{name}'"

        stub_method: Callable[..., Awaitable[Any]] = getattr(self._stub, name)

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper that ensures authentication before calling stub methods."""
            self._ensure_authenticated()
            return await stub_method(*args, **kwargs)

        # Preserve method metadata for better debugging
        wrapper.__name__ = name
        wrapper.__doc__ = stub_method.__doc__ or f"Forwarded method: {name}"

        return wrapper

    # Utility Methods
    def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated."""
        assert self.is_authenticated, "Client must be authenticated before making requests"

    async def get_status_summary(self) -> str:
        """Get formatted server status summary."""
        try:
            from .proto.clientpb import Empty, SessionRequest

            # Use dynamic API calls with proper types
            basic = await self.get_basic(Empty())
            sessions_response = await self.get_sessions(SessionRequest(all=True))
            listeners_response = await self.get_listeners(Empty())

            # Type-safe access to response fields
            sessions = {s.session_id: s for s in sessions_response.sessions}
            alive_sessions = {sid: s for sid, s in sessions.items() if s.is_alive}
            listeners = listeners_response.listeners

            return (
                f"Malice Network Server Status:\n"
                f"  Version: {basic.version}\n"
                f"  Sessions: {len(sessions)} total, {len(alive_sessions)} alive\n"
                f"  Listeners: {len(listeners)}\n"
                f"  Operator: {self.config.operator}"
            )
        except Exception as e:
            return f"Failed to get status: {e}"

    # Management Methods (similar to Go server.go)
    async def update(self) -> None:
        """Update all managed collections from server."""
        await self.update_sessions()
        await self.update_listeners()
        await self.update_pipelines()

    async def update_sessions(self, all: bool = False) -> None:
        """Update sessions collection from server."""
        from .proto.clientpb import SessionRequest
        response = await self.get_sessions(SessionRequest(all=all))

        # Update local cache
        self._sessions.clear()
        for session in response.sessions:
            self._sessions[session.session_id] = session

    async def update_listeners(self) -> None:
        """Update listeners collection from server."""
        from .proto.clientpb import Empty
        response = await self.get_listeners(Empty())

        # Update local cache
        self._listeners.clear()
        for listener in response.listeners:
            self._listeners[listener.id] = listener

    async def update_pipelines(self) -> None:
        """Update pipelines collection from server."""
        from .proto.clientpb import Empty
        response = await self.list_jobs(Empty())

        # Update local cache
        self._pipelines.clear()
        for pipeline in response.pipelines:
            self._pipelines[pipeline.name] = pipeline

    # Session Management Methods
    async def add_session(self, session: Session) -> Session:
        """Add session to local cache and return it."""
        self._sessions[session.session_id] = session
        return session

    async def get_local_session(self, session_id: str) -> Optional[Session]:
        """Get session from local cache by session_id."""
        return self._sessions.get(session_id)

    async def remove_session(self, session_id: str) -> bool:
        """Remove session from local cache."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def get_alive_sessions(self) -> Dict[str, Session]:
        """Get all alive sessions from cache."""
        return {sid: session for sid, session in self._sessions.items() if session.is_alive}

    async def get_session_by_note(self, note: str) -> Optional[Session]:
        """Get session by note field."""
        for session in self._sessions.values():
            if session.note == note:
                return session
        return None

    # Listener Management Methods
    async def add_listener(self, listener: Listener) -> Listener:
        """Add listener to local cache and return it."""
        self._listeners[listener.listener_id] = listener
        return listener

    async def get_local_listener(self, listener_id: str) -> Optional[Listener]:
        """Get listener from local cache by listener_id."""
        return self._listeners.get(listener_id)

    async def remove_listener(self, listener_id: str) -> bool:
        """Remove listener from local cache."""
        if listener_id in self._listeners:
            del self._listeners[listener_id]
            return True
        return False

    # Pipeline Management Methods
    async def add_pipeline(self, pipeline: Pipeline) -> Pipeline:
        """Add pipeline to local cache and return it."""
        self._pipelines[pipeline.name] = pipeline
        return pipeline

    async def get_local_pipeline(self, name: str) -> Optional[Pipeline]:
        """Get pipeline from local cache by name."""
        return self._pipelines.get(name)

    async def remove_pipeline(self, name: str) -> bool:
        """Remove pipeline from local cache."""
        if name in self._pipelines:
            del self._pipelines[name]
            return True
        return False

    # Utility Methods for State Management
    async def clear_all_caches(self) -> None:
        """Clear all local caches."""
        self._sessions.clear()
        self._listeners.clear()
        self._pipelines.clear()
        self._clients.clear()

    async def refresh_target_session(self) -> Optional[Session]:
        """Refresh and return the currently active target session."""
        if not self._active_target:
            return None

        from .proto.clientpb import SessionRequest
        response = await self.get_session(SessionRequest(session_id=self._active_target))
        self._sessions[self._active_target] = response
        return response

    async def set_active_session(self, session_id: str, refresh: bool = True) -> Optional[Session]:
        """Set active target session and optionally refresh it."""
        self._active_target = session_id

        if refresh:
            return await self.refresh_target_session()
        else:
            return await self.get_local_session(session_id)

    async def sync_with_server(self) -> None:
        """Synchronize all local state with server."""
        await self.update()


# Convenience functions
async def connect(config_path: Union[str, Path]) -> MaliceClient:
    """Quick connection helper."""
    client = MaliceClient.from_config_file(config_path)
    await client.connect()
    return client

@asynccontextmanager
async def connect_context(config_path: Union[str, Path]) -> AsyncContextManager[MaliceClient]:
    """Context manager for connections."""
    async with MaliceClient.from_config_file(config_path) as client:
        yield client