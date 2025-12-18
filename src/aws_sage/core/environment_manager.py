"""Environment manager for AWS MCP Pro.

Manages switching between production AWS and LocalStack environments.
"""

import socket
from dataclasses import dataclass
from typing import ClassVar

from aws_sage.core.environment import (
    DEFAULT_LOCALSTACK_CONFIG,
    DEFAULT_PRODUCTION_CONFIG,
    LOCALSTACK_COMMUNITY_SERVICES,
    LOCALSTACK_PRO_SERVICES,
    EnvironmentConfig,
    EnvironmentType,
)


@dataclass
class EnvironmentSwitchResult:
    """Result of switching environments."""

    success: bool
    environment: EnvironmentConfig | None
    message: str
    warnings: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "environment": self.environment.to_dict() if self.environment else None,
            "message": self.message,
            "warnings": self.warnings,
        }


class EnvironmentManager:
    """Manages AWS environment configurations and switching."""

    _instance: ClassVar["EnvironmentManager | None"] = None
    _environments: dict[str, EnvironmentConfig]
    _active_environment: str

    def __init__(self) -> None:
        """Initialize with default environments."""
        self._environments = {
            "production": DEFAULT_PRODUCTION_CONFIG,
            "localstack": DEFAULT_LOCALSTACK_CONFIG,
        }
        self._active_environment = "production"
        self._environments["production"].is_active = True

    @classmethod
    def get_instance(cls) -> "EnvironmentManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = EnvironmentManager()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    def list_environments(self) -> list[EnvironmentConfig]:
        """List all configured environments."""
        return list(self._environments.values())

    def get_environment(self, name: str) -> EnvironmentConfig | None:
        """Get a specific environment by name."""
        return self._environments.get(name)

    def get_active_environment(self) -> EnvironmentConfig:
        """Get the currently active environment."""
        return self._environments[self._active_environment]

    def is_localstack(self) -> bool:
        """Check if currently using LocalStack."""
        return self.get_active_environment().type == EnvironmentType.LOCALSTACK

    def is_production(self) -> bool:
        """Check if currently using production AWS."""
        return self.get_active_environment().type == EnvironmentType.PRODUCTION

    def add_environment(self, config: EnvironmentConfig) -> None:
        """Add a custom environment configuration."""
        self._environments[config.name] = config

    def switch_environment(
        self, name: str, validate: bool = True
    ) -> EnvironmentSwitchResult:
        """Switch to a different environment.

        Args:
            name: Name of the environment to switch to
            validate: Whether to validate connectivity before switching

        Returns:
            EnvironmentSwitchResult with success status and any warnings
        """
        warnings: list[str] = []

        # Check if environment exists
        if name not in self._environments:
            available = list(self._environments.keys())
            return EnvironmentSwitchResult(
                success=False,
                environment=None,
                message=f"Environment '{name}' not found. Available: {available}",
                warnings=[],
            )

        target_env = self._environments[name]

        # Warn when switching to production
        if target_env.type == EnvironmentType.PRODUCTION:
            warnings.append(
                "WARNING: Switching to PRODUCTION environment. "
                "Operations will affect real AWS resources."
            )

        # Validate connectivity if requested
        if validate and target_env.type == EnvironmentType.LOCALSTACK:
            if not self._check_localstack_connectivity(target_env):
                return EnvironmentSwitchResult(
                    success=False,
                    environment=None,
                    message=(
                        f"Cannot connect to LocalStack at {target_env.endpoint_url}. "
                        "Is LocalStack running? Try: docker compose up -d localstack"
                    ),
                    warnings=[],
                )

        # Deactivate current environment
        self._environments[self._active_environment].is_active = False

        # Activate new environment
        self._active_environment = name
        target_env.is_active = True

        return EnvironmentSwitchResult(
            success=True,
            environment=target_env,
            message=f"Switched to '{name}' environment",
            warnings=warnings,
        )

    def _check_localstack_connectivity(
        self, config: EnvironmentConfig, timeout: float = 2.0
    ) -> bool:
        """Check if LocalStack is reachable.

        Args:
            config: LocalStack environment configuration
            timeout: Connection timeout in seconds

        Returns:
            True if LocalStack is reachable
        """
        if not config.endpoint_url:
            return False

        try:
            # Parse host and port from endpoint URL
            url = config.endpoint_url.replace("http://", "").replace("https://", "")
            parts = url.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 4566

            # Try to connect
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except (OSError, ValueError):
            return False

    def check_localstack(self) -> dict:
        """Check LocalStack status and available services.

        Returns:
            Dictionary with LocalStack status information
        """
        localstack_env = self._environments.get("localstack")
        if not localstack_env:
            return {
                "available": False,
                "message": "LocalStack environment not configured",
            }

        is_reachable = self._check_localstack_connectivity(localstack_env)

        return {
            "available": is_reachable,
            "endpoint_url": localstack_env.endpoint_url,
            "community_services": sorted(LOCALSTACK_COMMUNITY_SERVICES),
            "pro_services": sorted(LOCALSTACK_PRO_SERVICES),
            "message": (
                "LocalStack is running and accessible"
                if is_reachable
                else f"LocalStack not reachable at {localstack_env.endpoint_url}"
            ),
        }

    def get_client_kwargs(self, service: str, region: str | None = None) -> dict:
        """Get boto3 client kwargs for the active environment.

        Args:
            service: AWS service name
            region: Optional region override

        Returns:
            Dictionary of kwargs to pass to boto3.client()
        """
        env = self.get_active_environment()
        kwargs = env.get_client_kwargs(service)

        if region:
            kwargs["region_name"] = region

        return kwargs

    def is_service_available(self, service: str) -> tuple[bool, str]:
        """Check if a service is available in the active environment.

        Args:
            service: AWS service name

        Returns:
            Tuple of (is_available, message)
        """
        env = self.get_active_environment()

        if env.is_service_available(service):
            return True, f"Service '{service}' is available"

        if service.lower() in LOCALSTACK_PRO_SERVICES:
            return (
                False,
                f"Service '{service}' requires LocalStack Pro. "
                "Consider switching to production or upgrading LocalStack.",
            )

        return (
            False,
            f"Service '{service}' is not available in LocalStack Community. "
            "Consider switching to production.",
        )

    def get_environment_info(self) -> dict:
        """Get detailed information about the current environment.

        Returns:
            Dictionary with environment details
        """
        env = self.get_active_environment()

        info = {
            "name": env.name,
            "type": env.type.value,
            "is_production": self.is_production(),
            "is_localstack": self.is_localstack(),
            "region": env.region,
            "description": env.description,
        }

        if env.type == EnvironmentType.LOCALSTACK:
            info["endpoint_url"] = env.endpoint_url
            info["available_services_count"] = len(env.available_services)
            info["is_reachable"] = self._check_localstack_connectivity(env)

        return info


# Global singleton accessor
def get_environment_manager() -> EnvironmentManager:
    """Get the global EnvironmentManager instance."""
    return EnvironmentManager.get_instance()


def reset_environment_manager() -> None:
    """Reset the global EnvironmentManager instance (for testing)."""
    EnvironmentManager.reset_instance()
