"""
Malice Network Client Configuration

This module handles client configuration loading from various sources,
including YAML files and authentication files.
"""

import yaml
from pathlib import Path
from typing import Union, Dict, Any
from pydantic import BaseModel, Field, validator

from .exceptions import ConfigurationError


class ClientConfig(BaseModel):
    """Configuration for Malice Network client connections."""

    operator: str = Field(..., description="Operator name for authentication")
    host: str = Field(..., description="Server hostname or IP address")
    port: int = Field(..., ge=1, le=65535, description="Server port number")
    ca_certificate: str = Field(..., description="CA certificate for mTLS")
    certificate: str = Field(..., description="Client certificate for mTLS")
    private_key: str = Field(..., description="Client private key for mTLS")
    type: str = Field(default="client", description="Configuration type")

    class Config:
        """Pydantic model configuration."""
        validate_assignment = True
        str_strip_whitespace = True
        frozen = False

    @validator('operator')
    def validate_operator(cls, v):
        """Validate operator name."""
        if not v or not v.strip():
            raise ValueError("Operator name cannot be empty")
        return v.strip()

    @validator('host')
    def validate_host(cls, v):
        """Validate host address."""
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()

    @validator('ca_certificate', 'certificate', 'private_key')
    def validate_certificates(cls, v):
        """Validate certificate/key fields."""
        if not v or not v.strip():
            raise ValueError("Certificate/key cannot be empty")
        return v.strip()

    def address(self) -> str:
        """Return the server address in host:port format."""
        return f"{self.host}:{self.port}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConfig":
        """Create configuration from dictionary."""
        try:
            # Map old key names to new field names
            config_data = {
                "operator": data["operator"],
                "host": data["host"],
                "port": int(data["port"]),
                "ca_certificate": data.get("ca", data.get("ca_certificate", "")),
                "certificate": data.get("cert", data.get("certificate", "")),
                "private_key": data.get("key", data.get("private_key", "")),
                "type": data.get("type", "client")
            }
            return cls(**config_data)
        except KeyError as e:
            raise ConfigurationError(f"Missing required configuration key: {e}")
        except Exception as e:
            raise ConfigurationError(f"Invalid configuration: {e}")

    @classmethod
    def from_yaml_file(cls, file_path: Union[str, Path]) -> "ClientConfig":
        """Load configuration from YAML file."""
        file_path = Path(file_path)

        if not file_path.exists():
            raise ConfigurationError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                raise ConfigurationError("Configuration file is empty")

            return cls.from_dict(data)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration file: {e}")
        except IOError as e:
            raise ConfigurationError(f"Failed to read configuration file: {e}")

    @classmethod
    def from_auth_file(cls, file_path: Union[str, Path]) -> "ClientConfig":
        """Load configuration from .auth file format."""
        return cls.from_yaml_file(file_path)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "operator": self.operator,
            "host": self.host,
            "port": self.port,
            "ca": self.ca_certificate,
            "cert": self.certificate,
            "key": self.private_key,
            "type": self.type
        }

    def save_to_file(self, file_path: Union[str, Path]) -> None:
        """Save configuration to YAML file."""
        file_path = Path(file_path)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.to_dict(), f, default_flow_style=False)
        except IOError as e:
            raise ConfigurationError(f"Failed to save configuration file: {e}")

    def model_dump_for_auth(self) -> Dict[str, Any]:
        """Export configuration in auth file format."""
        return self.to_dict()

    def model_dump_json_for_auth(self) -> str:
        """Export configuration as JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2)


# Convenience functions for backward compatibility
def parse_config_file(file_path: Union[str, Path]) -> ClientConfig:
    """Parse configuration file (supports both .yaml and .auth formats)."""
    return ClientConfig.from_auth_file(file_path)


def read_config(file_path: Union[str, Path]) -> ClientConfig:
    """Read configuration from file."""
    return ClientConfig.from_yaml_file(file_path)


def write_config(config: ClientConfig, file_path: Union[str, Path]) -> None:
    """Write configuration to file."""
    config.save_to_file(file_path)