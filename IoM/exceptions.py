"""
Malice Network SDK Exceptions

This module defines custom exceptions for the Malice Network SDK to provide
clear error handling and debugging information.
"""


class MaliceError(Exception):
    """Base exception for all Malice Network SDK errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConnectionError(MaliceError):
    """Raised when connection to the Malice Network server fails."""
    pass


class AuthenticationError(MaliceError):
    """Raised when authentication with the server fails."""
    pass


class SessionError(MaliceError):
    """Raised when session-related operations fail."""

    def __init__(self, message: str, session_id: str = None, details: str = None):
        self.session_id = session_id
        super().__init__(message, details)

    def __str__(self):
        base_msg = super().__str__()
        if self.session_id:
            return f"{base_msg} (Session: {self.session_id[:8]}...)"
        return base_msg


class TaskError(MaliceError):
    """Raised when task execution fails."""

    def __init__(self, message: str, task_id: str = None, session_id: str = None, details: str = None):
        self.task_id = task_id
        self.session_id = session_id
        super().__init__(message, details)

    def __str__(self):
        base_msg = super().__str__()
        parts = []
        if self.task_id:
            parts.append(f"Task: {self.task_id}")
        if self.session_id:
            parts.append(f"Session: {self.session_id[:8]}...")

        if parts:
            return f"{base_msg} ({', '.join(parts)})"
        return base_msg


class ConfigurationError(MaliceError):
    """Raised when configuration is invalid or missing."""
    pass


class TimeoutError(MaliceError):
    """Raised when operations timeout."""

    def __init__(self, message: str, timeout: float, details: str = None):
        self.timeout = timeout
        super().__init__(message, details)

    def __str__(self):
        base_msg = super().__str__()
        return f"{base_msg} (Timeout: {self.timeout}s)"


class ProtocolError(MaliceError):
    """Raised when protocol-level errors occur."""
    pass