"""Plugin system for custom transcription providers and extensions.

Plugins are Python modules placed in the plugin directory. Each plugin
must define a ``register(manager)`` function that receives a
:class:`~bits_whisperer.core.provider_manager.ProviderManager` and
registers custom providers via ``manager.register(key, instance)``.

Plugin directory
----------------
By default, plugins live in ``DATA_DIR/plugins/``. Users can override
this in Settings under Plugin Settings.

Plugin structure
----------------
A plugin is a ``.py`` file or a package (directory with ``__init__.py``)
in the plugin directory. Each must implement::

    def register(manager: ProviderManager) -> None:
        '''Register this plugin's providers with the manager.'''
        manager.register("my_custom_provider", MyProvider())

Plugin metadata (optional)::

    PLUGIN_NAME = "My Custom Provider"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_AUTHOR = "Author Name"
    PLUGIN_DESCRIPTION = "A custom transcription provider."
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bits_whisperer.utils.constants import DATA_DIR

if TYPE_CHECKING:
    from bits_whisperer.core.provider_manager import ProviderManager
    from bits_whisperer.core.settings import PluginSettings

logger = logging.getLogger(__name__)

# Default plugin directory
PLUGINS_DIR = DATA_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class PluginInfo:
    """Metadata about a discovered plugin."""

    name: str
    module_name: str
    path: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    is_loaded: bool = False
    is_enabled: bool = True
    error: str = ""


class PluginManager:
    """Discovers, loads, and manages plugins.

    The plugin manager scans the plugin directory for Python modules
    and packages, loads them, and calls their ``register()`` function
    to integrate with the provider system.
    """

    def __init__(
        self,
        settings: PluginSettings,
        provider_manager: ProviderManager,
    ) -> None:
        """Initialise the plugin manager.

        Args:
            settings: Plugin configuration settings.
            provider_manager: Provider manager for registering providers.
        """
        self._settings = settings
        self._provider_manager = provider_manager
        self._plugins: dict[str, PluginInfo] = {}
        self._plugin_dir = Path(settings.plugin_directory) if settings.plugin_directory else PLUGINS_DIR

        # Ensure plugin directory exists
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def discover(self) -> list[PluginInfo]:
        """Scan the plugin directory for available plugins.

        Returns:
            List of discovered plugin metadata.
        """
        if not self._settings.enabled:
            return []

        self._plugins.clear()

        if not self._plugin_dir.exists():
            return []

        # Scan for .py files
        for py_file in sorted(self._plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            info = self._inspect_plugin_file(py_file)
            if info:
                self._plugins[info.module_name] = info

        # Scan for packages (directories with __init__.py)
        for pkg_dir in sorted(self._plugin_dir.iterdir()):
            if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
                if pkg_dir.name.startswith("_"):
                    continue
                info = self._inspect_plugin_package(pkg_dir)
                if info:
                    self._plugins[info.module_name] = info

        # Mark disabled plugins
        for mod_name in self._settings.disabled_plugins:
            if mod_name in self._plugins:
                self._plugins[mod_name].is_enabled = False

        discovered = list(self._plugins.values())
        logger.info("Discovered %d plugins", len(discovered))
        return discovered

    def load_all(self) -> int:
        """Load and register all enabled plugins.

        Returns:
            Number of plugins successfully loaded.
        """
        if not self._settings.enabled:
            return 0

        if not self._plugins:
            self.discover()

        loaded = 0
        for info in self._plugins.values():
            if info.is_enabled and not info.is_loaded:
                if self._load_plugin(info):
                    loaded += 1

        logger.info("Loaded %d/%d plugins", loaded, len(self._plugins))
        return loaded

    def load_plugin(self, module_name: str) -> bool:
        """Load a single plugin by module name.

        Args:
            module_name: The module name to load.

        Returns:
            True if loaded successfully.
        """
        info = self._plugins.get(module_name)
        if not info:
            return False
        return self._load_plugin(info)

    def unload_plugin(self, module_name: str) -> bool:
        """Unload a plugin (removes from active providers).

        Args:
            module_name: The module name to unload.

        Returns:
            True if unloaded successfully.
        """
        info = self._plugins.get(module_name)
        if not info or not info.is_loaded:
            return False

        info.is_loaded = False
        info.is_enabled = False
        logger.info("Unloaded plugin: %s", info.name)
        return True

    def enable_plugin(self, module_name: str) -> None:
        """Enable a plugin.

        Args:
            module_name: The module name to enable.
        """
        info = self._plugins.get(module_name)
        if info:
            info.is_enabled = True
            if module_name in self._settings.disabled_plugins:
                self._settings.disabled_plugins.remove(module_name)

    def disable_plugin(self, module_name: str) -> None:
        """Disable a plugin.

        Args:
            module_name: The module name to disable.
        """
        info = self._plugins.get(module_name)
        if info:
            info.is_enabled = False
            if module_name not in self._settings.disabled_plugins:
                self._settings.disabled_plugins.append(module_name)

    def list_plugins(self) -> list[PluginInfo]:
        """Return all discovered plugins.

        Returns:
            List of PluginInfo objects.
        """
        return list(self._plugins.values())

    def get_plugin_dir(self) -> Path:
        """Return the current plugin directory path.

        Returns:
            Plugin directory Path.
        """
        return self._plugin_dir

    # ------------------------------------------------------------------ #
    # Internal methods                                                     #
    # ------------------------------------------------------------------ #

    def _inspect_plugin_file(self, path: Path) -> PluginInfo | None:
        """Extract metadata from a plugin .py file without importing.

        Args:
            path: Path to the .py file.

        Returns:
            PluginInfo or None if not a valid plugin.
        """
        try:
            source = path.read_text("utf-8")

            # Check for required register function
            if "def register(" not in source:
                return None

            # Extract optional metadata
            name = path.stem.replace("_", " ").title()
            version = "1.0.0"
            author = ""
            description = ""

            for line in source.splitlines():
                line = line.strip()
                if line.startswith("PLUGIN_NAME"):
                    name = self._extract_string(line)
                elif line.startswith("PLUGIN_VERSION"):
                    version = self._extract_string(line)
                elif line.startswith("PLUGIN_AUTHOR"):
                    author = self._extract_string(line)
                elif line.startswith("PLUGIN_DESCRIPTION"):
                    description = self._extract_string(line)

            return PluginInfo(
                name=name,
                module_name=path.stem,
                path=str(path),
                version=version,
                author=author,
                description=description,
            )
        except Exception as exc:
            logger.debug("Could not inspect plugin %s: %s", path, exc)
            return None

    def _inspect_plugin_package(self, pkg_dir: Path) -> PluginInfo | None:
        """Extract metadata from a plugin package directory.

        Args:
            pkg_dir: Path to the package directory.

        Returns:
            PluginInfo or None if not a valid plugin.
        """
        init_path = pkg_dir / "__init__.py"
        return self._inspect_plugin_file(init_path)

    def _load_plugin(self, info: PluginInfo) -> bool:
        """Import a plugin module and call its register() function.

        Args:
            info: Plugin metadata.

        Returns:
            True if loaded successfully.
        """
        try:
            path = Path(info.path)

            # Add plugin directory to sys.path temporarily
            plugin_parent = str(path.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)

            # Load the module
            if path.name == "__init__.py":
                # Package plugin
                module_name = f"bw_plugin_{path.parent.name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, str(path),
                    submodule_search_locations=[str(path.parent)],
                )
            else:
                module_name = f"bw_plugin_{info.module_name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, str(path),
                )

            if spec is None or spec.loader is None:
                info.error = "Could not create module spec"
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Call register()
            register_fn = getattr(module, "register", None)
            if register_fn is None:
                info.error = "No register() function found"
                return False

            register_fn(self._provider_manager)
            info.is_loaded = True
            info.error = ""
            logger.info("Loaded plugin: %s v%s", info.name, info.version)
            return True

        except Exception as exc:
            info.error = str(exc)
            logger.warning("Failed to load plugin '%s': %s", info.name, exc)
            return False

    @staticmethod
    def _extract_string(line: str) -> str:
        """Extract a string value from an assignment line.

        Args:
            line: Line like 'PLUGIN_NAME = "My Plugin"'.

        Returns:
            Extracted string value.
        """
        if "=" in line:
            val = line.split("=", 1)[1].strip()
            val = val.strip("\"'")
            return val
        return ""
