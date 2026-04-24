# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from abc import ABC
import logging
import os
import sys
from typing import Any, Callable


class SystemPlatform(ABC):
	"""Base platform hooks used by the launcher and core."""

	name = "unknown"

	def apply_early_monkey_patches(self, monkeyPatchesModule: Any) -> None:
		pass

	def resolve_app_dir(self, *, running_as_source: bool, module_path: str) -> str:
		if not running_as_source:
			# Append the path of the executable so modules can be imported from packaged builds.
			sys.path.append(sys.prefix)
			return os.path.abspath(sys.prefix)
		return os.path.abspath(os.path.dirname(module_path))

	def show_error(self, title: str, message: str) -> None:
		print(f"{title}: {message}", file=sys.stderr)

	def detect_is_appx(self) -> bool:
		return False

	def is_runtime_supported(self) -> bool:
		return True

	def get_runtime_unsupported_message(self) -> str:
		return f"NVDA runtime is not implemented for platform: {self.name}"

	def ensure_supported_os(self) -> None:
		pass

	def find_running_instance(
		self,
		logger: logging.Logger,
		window_class_name: str,
		window_title: str,
	) -> int:
		return 0

	def terminate_running_instance(self, window: int) -> None:
		raise RuntimeError(f"Platform {self.name} does not implement process replacement")

	def acquire_single_instance_mutex(
		self,
		desktop_name: str,
		logger: logging.Logger,
	) -> object | None:
		raise RuntimeError(f"Platform {self.name} does not implement single-instance coordination")

	def release_single_instance_mutex(self, mutex: object, log: Any) -> None:
		pass

	def get_desktop_name(self) -> str:
		return "default"

	def is_running_on_secure_desktop(self) -> bool:
		return False

	def apply_secure_desktop_policy(
		self,
		*,
		app_args: Any,
		is_secure_desktop: bool,
		service_debug_enabled: bool,
		sys_prefix: str,
	) -> None:
		if not is_secure_desktop:
			return
		if not service_debug_enabled:
			app_args.secure = True
		app_args.changeScreenReaderFlag = False
		app_args.minimal = True
		app_args.configPath = os.path.join(sys_prefix, "systemConfig")

	def prepare_for_core(
		self,
		*,
		app_args: Any,
		is_secure_desktop: bool,
		is_appx: bool,
		log: Any,
	) -> None:
		pass

	def cleanup_after_core(
		self,
		*,
		app_args: Any,
		is_secure_desktop: bool,
		is_appx: bool,
		log: Any,
	) -> None:
		pass

	def initialize_dpi_awareness(self, *, running_as_source: bool) -> None:
		pass

	def initialize_object_caches(self) -> None:
		raise RuntimeError(f"Platform {self.name} does not implement object cache initialization")

	def log_runtime_info(self, log: Any) -> None:
		log.info(f"Platform: {sys.platform}")

	def initialize_platform_bootstrap_runtime(
		self,
		*,
		app_args: Any,
		config: Any,
		app_dir: str,
		log: Any,
	) -> object | None:
		return None

	def terminate_platform_bootstrap_runtime(
		self,
		runtime: object | None,
		terminate: Callable[..., None],
		*,
		app_args: Any,
		config: Any,
		app_dir: str,
		log: Any,
	) -> None:
		pass

	def uses_headless_core_runtime(self) -> bool:
		return False

	def initialize_core_runtime(
		self,
		*,
		bootstrap_runtime: object | None,
		log: Any,
	) -> object | None:
		return None

	def initialize_core_runtime_monitoring(self, runtime: object | None, log: Any) -> None:
		pass

	def finalize_core_runtime_startup(self, runtime: object | None, log: Any) -> None:
		pass

	def run_headless_core_loop(self, runtime: object | None, log: Any) -> None:
		raise RuntimeError(f"Platform {self.name} does not implement a headless core runtime loop")

	def pump_core_runtime(
		self,
		runtime: object | None,
		*,
		queue_pump: Callable[[], None],
		braille_pump: Callable[[], None],
		vision_pump: Callable[[], None],
	) -> None:
		queue_pump()
		braille_pump()
		vision_pump()

	def cleanup_before_gui_exit(self, terminate: Callable[..., None]) -> None:
		pass

	def terminate_core_runtime(
		self,
		runtime: object | None,
		terminate: Callable[..., None],
		log: Any,
	) -> None:
		pass


class UnsupportedPlatform(SystemPlatform):
	"""Placeholder used until a concrete platform backend exists."""

	def __init__(self, platform_name: str):
		self.name = platform_name

	def is_runtime_supported(self) -> bool:
		return False

	def ensure_supported_os(self) -> None:
		raise RuntimeError(f"NVDA platform backend is not implemented for {self.name}")
