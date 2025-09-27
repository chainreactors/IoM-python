"""
Malice Network Python SDK

Modern async Python client library for the Malice Network C2 Framework.

Key Features:
- 🚀 Async/Await - Modern Python async support
- 🔒 Type Safety - Complete type hints with IDE support
- 🎯 Dynamic API - Automatic forwarding to all gRPC methods
- 🛡️ mTLS Security - Secure client authentication
- ⚡ Session Management - Automatic session context handling

Quick Start:
    import asyncio
    from IoM import MaliceClient

    async def main():
        client = MaliceClient.from_config_file("client.auth")
        async with client:
            # Get server status
            status = await client.get_status_summary()
            print(status)

            # Work with sessions
            await client.update_sessions()
            if client.cached_sessions:
                session_id = list(client.cached_sessions.keys())[0]
                session = client.sessions.get(session_id)

                # Execute commands with automatic session context
                from IoM.proto.modulepb import Request
                await session.whoami(Request())

    asyncio.run(main())
"""

__version__ = "0.1.0"
__author__ = "ChainReactors"

# Core client classes
from .client import MaliceClient, connect, connect_context
from .config import ClientConfig
from .session import MaliceSession, SessionManager
from .exceptions import (
    MaliceError,
    ConnectionError,
    AuthenticationError,
    SessionError,
    TaskError,
    ConfigurationError,
)

# Proto imports for convenience (these may not exist until proto generation)
try:
    from .proto import clientpb, clientrpc, modulepb
    _PROTO_AVAILABLE = True
except ImportError:
    clientpb = None
    clientrpc = None
    modulepb = None
    _PROTO_AVAILABLE = False

__all__ = [
    # Client classes
    "MaliceClient",
    "connect",
    "connect_context",
    "ClientConfig",

    # Session management
    "MaliceSession",
    "SessionManager",

    # Exceptions
    "MaliceError",
    "ConnectionError",
    "AuthenticationError",
    "SessionError",
    "TaskError",
    "ConfigurationError",

    # Proto modules (if available)
    "clientpb",
    "clientrpc",
    "modulepb",
]