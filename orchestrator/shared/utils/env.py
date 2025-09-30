"""
Environment variable utilities
"""

import os
import logging
from typing import Optional, Dict, Any, List, overload
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass

class EnvConfig:
    """Environment configuration container"""
    # GCP Configuration
    gcp_project: str
    gcp_region: str = "us-central1"

    # API Keys (read from Secret Manager in production)
    tiingo_api_key: Optional[str] = None
    finnhub_api_key: Optional[str] = None
    polygon_api_key: Optional[str] = None
    alphavantage_api_key: Optional[str] = None

    # Service URLs (for orchestrator)
    tiingo_service_url: str = "http://tiingo-service"
    finnhub_service_url: str = "http://finnhub-service"
    polygon_service_url: str = "http://polygon-service"
    alphavantage_service_url: str = "http://alphavantage-service"

    # Firestore Configuration
    firestore_emulator_host: Optional[str] = None

    # Service Account Email (for OIDC verification)
    scheduler_service_account: Optional[str] = None

    # Rate Limiting
    max_concurrent_requests: int = 10
    default_rate_limit_delay: int = 1

    # Logging
    log_level: str = "INFO"

    # Development flags
    dev_mode: bool = False
    skip_auth: bool = False


class EnvironmentError(Exception):
    """Raised when required environment variables are missing"""
    pass


def get_required_env(key: str, description: str = "") -> str:
    """
    Get a required environment variable

    Args:
        key: Environment variable name
        description: Optional description for error messages

    Returns:
        Environment variable value

    Raises:
        EnvironmentError: If the environment variable is not set
    """
    value = os.getenv(key)
    if value is None:
        error_msg = f"Required environment variable {key} is not set"
        if description:
            error_msg += f" ({description})"
        logger.error(error_msg)
        raise EnvironmentError(error_msg)
    return value


@overload

def get_optional_env(key: str) -> Optional[str]: ...

@overload

def get_optional_env(key: str, default: str) -> str: ...

def get_optional_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get an optional environment variable

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Environment variable value or default
    """
    return os.getenv(key, default)


def get_bool_env(key: str, default: bool = False) -> bool:
    """
    Get a boolean environment variable

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Boolean value
    """
    value = os.getenv(key, "").lower()
    return value in ("true", "1", "yes", "on") if value else default


def get_int_env(key: str, default: int) -> int:
    """
    Get an integer environment variable

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value
    """
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        logger.warning(f"Invalid integer value for {key}, using default: {default}")
        return default


def load_env_config() -> EnvConfig:
    """
    Load environment configuration

    Returns:
        EnvConfig instance with all environment variables loaded

    Raises:
        EnvironmentError: If required variables are missing
    """
    try:
        config = EnvConfig(
            # Required
            gcp_project=get_required_env("GCP_PROJECT", "Google Cloud Project ID"),

            # Optional with defaults
            gcp_region=get_optional_env("GCP_REGION", "us-central1"),

            # API Keys (optional in dev mode with emulators)
            tiingo_api_key=get_optional_env("TIINGO_API_KEY"),
            finnhub_api_key=get_optional_env("FINNHUB_API_KEY"),
            polygon_api_key=get_optional_env("POLYGON_API_KEY"),
            alphavantage_api_key=get_optional_env("ALPHAVANTAGE_API_KEY"),

            # Service URLs
            tiingo_service_url=get_optional_env("TIINGO_SERVICE_URL", "http://tiingo-service"),
            finnhub_service_url=get_optional_env("FINNHUB_SERVICE_URL", "http://finnhub-service"),
            polygon_service_url=get_optional_env("POLYGON_SERVICE_URL", "http://polygon-service"),
            alphavantage_service_url=get_optional_env("ALPHAVANTAGE_SERVICE_URL", "http://alphavantage-service"),

            # Firestore
            firestore_emulator_host=get_optional_env("FIRESTORE_EMULATOR_HOST"),

            # Auth
            scheduler_service_account=get_optional_env("SCHEDULER_SERVICE_ACCOUNT"),

            # Performance
            max_concurrent_requests=get_int_env("MAX_CONCURRENT_REQUESTS", 10),
            default_rate_limit_delay=get_int_env("DEFAULT_RATE_LIMIT_DELAY", 1),

            # Logging
            log_level=get_optional_env("LOG_LEVEL", "INFO"),

            # Development
            dev_mode=get_bool_env("DEV_MODE", False),
            skip_auth=get_bool_env("SKIP_AUTH", False)
        )

        # Validate configuration
        validate_config(config)

        logger.info(f"Environment configuration loaded successfully")
        logger.info(f"GCP Project: {config.gcp_project}")
        logger.info(f"GCP Region: {config.gcp_region}")
        logger.info(f"Dev Mode: {config.dev_mode}")

        return config

    except Exception as e:
        logger.error(f"Failed to load environment configuration: {e}")
        raise


def validate_config(config: EnvConfig) -> None:
    """
    Validate environment configuration

    Args:
        config: EnvConfig instance to validate

    Raises:
        EnvironmentError: If configuration is invalid
    """
    errors = []

    # Check required fields
    if not config.gcp_project:
        errors.append("GCP_PROJECT is required")

    # In production mode, API key validation is done per-service at runtime
    # We don't validate all API keys upfront since each service only needs its own
    if not config.dev_mode:
        logger.info("Running in production mode - API keys will be validated per-service at runtime")

    # Validate URLs (only critical for orchestrator, but we'll validate format)
    service_urls = [
        ("tiingo_service_url", config.tiingo_service_url),
        ("finnhub_service_url", config.finnhub_service_url),
        ("polygon_service_url", config.polygon_service_url),
        ("alphavantage_service_url", config.alphavantage_service_url)
    ]

    for name, url in service_urls:
        if url and not url.startswith(("http://", "https://")):
            errors.append(f"Invalid service URL format for {name}: {url}")

    if errors:
        error_msg = "Environment configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
        raise EnvironmentError(error_msg)


def validate_service_config(config: EnvConfig, required_api_key: str) -> None:
    """
    Validate configuration for a specific service

    Args:
        config: EnvConfig instance to validate
        required_api_key: The API key required for this service (e.g., "tiingo_api_key")

    Raises:
        EnvironmentError: If service configuration is invalid
    """
    if not config.dev_mode:
        # Map config key to environment and secret names
        key_mappings = {
            "tiingo_api_key": ("TIINGO_API_KEY", "tiingo-api-key"),
            "finnhub_api_key": ("FINNHUB_API_KEY", "finnhub-api-key"),
            "polygon_api_key": ("POLYGON_API_KEY", "polygon-api-key"),
            "alphavantage_api_key": ("ALPHAVANTAGE_API_KEY", "alphavantage-api-key")
        }

        if required_api_key in key_mappings:
            current_value = getattr(config, required_api_key)
            if not current_value:
                env_key, secret_name = key_mappings[required_api_key]
                api_key = get_secret_from_env_or_secret_manager(
                    env_key, secret_name, config.gcp_project
                )
                if not api_key:
                    raise EnvironmentError(
                        f"{env_key} is required for this service in production mode"
                    )


def setup_logging(config: EnvConfig) -> None:
    """
    Setup logging based on configuration

    Args:
        config: EnvConfig instance
    """
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    # Setup basic logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set specific logger levels
    if config.dev_mode:
        # More verbose in dev mode
        logging.getLogger("shared").setLevel(logging.DEBUG)
        logging.getLogger("orchestrator").setLevel(logging.DEBUG)
    else:
        # Less verbose for external libraries in production
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("google").setLevel(logging.WARNING)


def get_secret_from_env_or_secret_manager(
    env_key: str,
    secret_name: str,
    project_id: str
) -> Optional[str]:
    """
    Get secret from environment variable first, then Secret Manager

    Args:
        env_key: Environment variable name
        secret_name: Secret Manager secret name
        project_id: GCP project ID

    Returns:
        Secret value or None if not found
    """
    # First try environment variable (for local dev)
    value = os.getenv(env_key)
    if value:
        return value

    # Then try Secret Manager (for production)
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except ImportError:
        logger.warning("google-cloud-secret-manager not installed, skipping Secret Manager lookup")
        return None
    except Exception as e:
        logger.warning(f"Failed to get secret {secret_name} from Secret Manager: {e}")
        return None


def load_api_keys(config: EnvConfig) -> Dict[str, Optional[str]]:
    """
    Load API keys from environment or Secret Manager

    Args:
        config: EnvConfig instance

    Returns:
        Dictionary of API keys
    """
    api_keys = {}

    key_mappings = [
        ("TIINGO_API_KEY", "tiingo-api-key", "tiingo_api_key"),
        ("FINNHUB_API_KEY", "finnhub-api-key", "finnhub_api_key"),
        ("POLYGON_API_KEY", "polygon-api-key", "polygon_api_key"),
        ("ALPHAVANTAGE_API_KEY", "alphavantage-api-key", "alphavantage_api_key")
    ]

    for env_key, secret_name, config_key in key_mappings:
        # Try to get from current config first
        current_value = getattr(config, config_key)
        if current_value:
            api_keys[config_key] = current_value
        else:
            # Try Secret Manager
            value = get_secret_from_env_or_secret_manager(
                env_key, secret_name, config.gcp_project
            )
            api_keys[config_key] = value

    return api_keys


# Module-level config instance
_config: Optional[EnvConfig] = None


def get_config() -> EnvConfig:
    """
    Get the global environment configuration

    Returns:
        EnvConfig instance
    """
    global _config
    if _config is None:
        _config = load_env_config()
    return _config


def set_config(config: EnvConfig) -> None:
    """
    Set the global environment configuration (mainly for testing)

    Args:
        config: EnvConfig instance to set
    """
    global _config
    _config = config