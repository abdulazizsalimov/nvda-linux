# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import logging
import os
from pathlib import Path
import sys
from typing import Any

from .base import SystemPlatform
import winBindings.kernel32
import winKernel
import winUser
from winBindings import user32


@dataclass
class WindowsCoreRuntime:
	JABHandler: Any
	winConsoleHandler: Any
	UIAHandler: Any
	IAccessibleHandler: Any
	inputCore: Any
	keyboardHandler: Any
	mouseHandler: Any
	touchHandler: Any
	watchdog: Any
	sessionTracking: Any


@dataclass
class WindowsBootstrapRuntime:
	NVDAHelper: Any
	nvwave: Any


class WindowsPlatform(SystemPlatform):
	name = "windows"

	def apply_early_monkey_patches(self, monkeyPatchesModule: Any) -> None:
		monkeyPatchesModule.applyMonkeyPatches()

	def resolve_app_dir(self, *, running_as_source: bool, module_path: str) -> str:
		if running_as_source:
			appDir = os.path.abspath(os.path.dirname(module_path))
			virtualEnv = os.getenv("VIRTUAL_ENV")
			if not virtualEnv or Path(appDir).parent != Path(virtualEnv).parent:
				user32.MessageBox(
					0,
					"NVDA cannot  detect the Python virtual environment. "
					"To run NVDA from source, please use runnvda.bat in the root of this repository.",
					"Error",
					winUser.MB_ICONERROR,
				)
				raise SystemExit(1)
			return appDir
		return super().resolve_app_dir(running_as_source=running_as_source, module_path=module_path)

	def show_error(self, title: str, message: str) -> None:
		winUser.MessageBox(0, message, title, winUser.MB_OK)

	def detect_is_appx(self) -> bool:
		try:
			getCurrentPackageFullName = winBindings.kernel32.GetCurrentPackageFullName
		except AttributeError:
			return False
		bufLen = ctypes.c_uint()
		# Error 15700 means the current process is not a Windows Store package.
		return getCurrentPackageFullName(ctypes.byref(bufLen), None) != 15700

	def ensure_supported_os(self) -> None:
		import winVersion

		if not winVersion.isSupportedOS():
			winUser.MessageBox(0, ctypes.FormatError(winUser.ERROR_OLD_WIN_VERSION), None, winUser.MB_ICONERROR)
			raise SystemExit(1)

	def find_running_instance(
		self,
		logger: logging.Logger,
		window_class_name: str,
		window_title: str,
	) -> int:
		try:
			oldAppWindowHandle = winUser.FindWindow(window_class_name, window_title)
		except WindowsError as e:
			logger.info("Can't find existing NVDA via Window Class")
			logger.debug(f"FindWindow error: {e}")
			return 0
		return oldAppWindowHandle if winUser.isWindow(oldAppWindowHandle) else 0

	def terminate_running_instance(self, window: int) -> None:
		processID, threadID = winUser.getWindowThreadProcessID(window)
		winUser.PostMessage(window, winUser.WM_QUIT, 0, 0)
		h = winKernel.openProcess(winKernel.SYNCHRONIZE, False, processID)
		if not h:
			# The process is already dead.
			return
		try:
			res = winKernel.waitForSingleObject(h, 4000)
			if res == 0:
				# The process terminated within the timeout period.
				return
		finally:
			winKernel.closeHandle(h)

		# The process is refusing to exit gracefully, so kill it forcefully.
		h = winKernel.openProcess(winKernel.PROCESS_TERMINATE | winKernel.SYNCHRONIZE, False, processID)
		if not h:
			raise OSError("Could not open process for termination")
		try:
			winKernel.TerminateProcess(h, 1)
			winKernel.waitForSingleObject(h, 2000)
		finally:
			winKernel.closeHandle(h)

	def acquire_single_instance_mutex(
		self,
		desktop_name: str,
		logger: logging.Logger,
	) -> object | None:
		mutex = winBindings.kernel32.CreateMutex(
			None,
			False,
			f"Local\\NVDA_{desktop_name}",
		)
		createMutexResult = winBindings.kernel32.GetLastError()
		if not mutex:
			logger.error(f"Unable to create mutex, last error: {createMutexResult}")
			raise winUser.WinError(createMutexResult)
		if createMutexResult == winKernel.ERROR_ALREADY_EXISTS:
			logger.debug("Waiting for prior NVDA to finish exiting")
		waitResult = winKernel.waitForSingleObject(
			mutex,
			2000,
		)

		logger.debug(f"Wait result: {waitResult}")
		if winKernel.WAIT_OBJECT_0 == waitResult:
			logger.info("Prior NVDA has finished exiting")
			return mutex
		if winKernel.WAIT_ABANDONED == waitResult:
			logger.error(
				"Prior NVDA exited without releasing mutex, taking ownership."
				" Note: Restarting your system is recommended."
				" This error indicates that NVDA previously did not exit correctly or was terminated"
				" (perhaps by the task manager).",
			)
			return mutex

		exception = None
		if winKernel.WAIT_TIMEOUT == waitResult:
			exception = Exception("Timeout exceeded waiting for mutex")
		elif winKernel.WAIT_FAILED == waitResult:
			waitError = winUser.GetLastError()
			logger.debug(f"Failed waiting for mutex, error: {waitError}")
			exception = winUser.WinError(waitError)
		releaseResult = winBindings.kernel32.ReleaseMutex(mutex)
		if 0 == releaseResult:
			releaseError = winUser.GetLastError()
			logger.debug(f"Failed to release mutex, error: {releaseError}")
		closeResult = winBindings.kernel32.CloseHandle(mutex)
		if 0 == closeResult:
			closeError = winUser.GetLastError()
			logger.debug(f"Failed to close mutex handle, error: {closeError}")
		if exception is not None:
			raise exception
		return None

	def release_single_instance_mutex(self, mutex: object, log: Any) -> None:
		releaseResult = winBindings.kernel32.ReleaseMutex(mutex)
		if 0 == releaseResult:
			releaseError = winUser.GetLastError()
			log.debug(f"Failed to release mutex, error: {releaseError}")
		res = winBindings.kernel32.CloseHandle(mutex)
		if 0 == res:
			error = winUser.GetLastError()
			log.error(f"Unable to close mutex handle, last error: {winUser.WinError(error)}")

	def get_desktop_name(self) -> str:
		UOI_NAME = 2  # The name of the object, as a string
		desktop = user32.GetThreadDesktop(
			winBindings.kernel32.GetCurrentThreadId(),
		)
		name = ctypes.create_unicode_buffer(256)
		user32.GetUserObjectInformation(
			desktop,
			UOI_NAME,
			ctypes.byref(name),
			ctypes.sizeof(name),
			None,
		)
		return name.value

	def is_running_on_secure_desktop(self) -> bool:
		return self.get_desktop_name() == "Winlogon"

	def prepare_for_core(
		self,
		*,
		app_args: Any,
		is_secure_desktop: bool,
		is_appx: bool,
		log: Any,
	) -> None:
		if app_args.changeScreenReaderFlag:
			winUser.setSystemScreenReaderFlag(True)

		# Accept WM_QUIT from other processes, even if running with higher privileges.
		if not user32.ChangeWindowMessageFilter(winUser.WM_QUIT, winUser.MSGFLT.ALLOW):
			log.error("Unable to set the NVDA process to receive WM_QUIT messages from other processes")
			raise winUser.WinError()

		# Make this the last application to be shut down and don't display a retry dialog box.
		winKernel.SetProcessShutdownParameters(0x100, winKernel.SHUTDOWN_NORETRY)
		if not is_secure_desktop and not is_appx:
			import easeOfAccess

			easeOfAccess.notify(3)

	def cleanup_after_core(
		self,
		*,
		app_args: Any,
		is_secure_desktop: bool,
		is_appx: bool,
		log: Any,
	) -> None:
		if not is_secure_desktop and not is_appx:
			import easeOfAccess

			easeOfAccess.notify(2)
		if app_args.changeScreenReaderFlag:
			winUser.setSystemScreenReaderFlag(False)

	def initialize_dpi_awareness(self, *, running_as_source: bool) -> None:
		if running_as_source:
			from winAPI.dpiAwareness import setDPIAwareness

			setDPIAwareness()

	def initialize_object_caches(self) -> None:
		import api
		import NVDAObjects

		desktopObject = NVDAObjects.window.Window(windowHandle=winUser.getDesktopWindow())
		api.setDesktopObject(desktopObject)
		api.setForegroundObject(desktopObject)
		api.setFocusObject(desktopObject)
		api.setNavigatorObject(desktopObject)
		api.setMouseObject(desktopObject)

	def log_runtime_info(self, log: Any) -> None:
		import winVersion

		log.info(f"Windows version: {winVersion.getWinVer()}")

	def initialize_platform_bootstrap_runtime(
		self,
		*,
		app_args: Any,
		config: Any,
		app_dir: str,
		log: Any,
	) -> WindowsBootstrapRuntime:
		import NVDAHelper
		import nvwave

		log.debug("Initializing NVDAHelper")
		NVDAHelper.initialize()

		log.debug("initializing nvwave")
		nvwave.initialize()
		if not app_args.minimal and config.conf["general"]["playStartAndExitSounds"]:
			try:
				nvwave.playWaveFile(os.path.join(app_dir, "waves", "start.wav"))
			except Exception:
				pass
		return WindowsBootstrapRuntime(
			NVDAHelper=NVDAHelper,
			nvwave=nvwave,
		)

	def terminate_platform_bootstrap_runtime(
		self,
		runtime: object | None,
		terminate,
		*,
		app_args: Any,
		config: Any,
		app_dir: str,
		log: Any,
	) -> None:
		if not isinstance(runtime, WindowsBootstrapRuntime):
			return
		if not app_args.minimal and config.conf["general"]["playStartAndExitSounds"]:
			try:
				runtime.nvwave.playWaveFile(
					os.path.join(app_dir, "waves", "exit.wav"),
					asynchronous=False,
				)
			except Exception:
				pass
		# We cannot terminate nvwave until after the exit sound is played.
		terminate(runtime.nvwave)
		terminate(runtime.NVDAHelper)

	def initialize_core_runtime(
		self,
		*,
		bootstrap_runtime: object | None,
		log: Any,
	) -> WindowsCoreRuntime:
		del bootstrap_runtime
		import JABHandler
		import winConsoleHandler
		import UIAHandler
		import IAccessibleHandler
		import inputCore
		import keyboardHandler
		import mouseHandler
		import touchHandler
		import watchdog
		from winAPI import sessionTracking

		runtime = WindowsCoreRuntime(
			JABHandler=JABHandler,
			winConsoleHandler=winConsoleHandler,
			UIAHandler=UIAHandler,
			IAccessibleHandler=IAccessibleHandler,
			inputCore=inputCore,
			keyboardHandler=keyboardHandler,
			mouseHandler=mouseHandler,
			touchHandler=touchHandler,
			watchdog=watchdog,
			sessionTracking=sessionTracking,
		)

		log.debug("initializing Java Access Bridge support")
		try:
			runtime.JABHandler.initialize()
			log.info("Java Access Bridge support initialized")
		except NotImplementedError:
			log.warning("Java Access Bridge not available")
		except:  # noqa: E722
			log.error("Error initializing Java Access Bridge support", exc_info=True)

		log.debug("Initializing legacy winConsole support")
		runtime.winConsoleHandler.initialize()

		log.debug("Initializing UIA support")
		try:
			runtime.UIAHandler.initialize()
		except RuntimeError:
			log.warning("UIA disabled in configuration")
		except:  # noqa: E722
			log.error("Error initializing UIA support", exc_info=True)

		log.debug("Initializing IAccessible support")
		runtime.IAccessibleHandler.initialize()

		log.debug("Initializing input core")
		runtime.inputCore.initialize()

		log.debug("Initializing keyboard handler")
		runtime.keyboardHandler.initialize(runtime.watchdog.WatchdogObserver())

		log.debug("initializing mouse handler")
		runtime.mouseHandler.initialize()

		log.debug("Initializing touchHandler")
		try:
			runtime.touchHandler.initialize()
		except NotImplementedError:
			pass

		return runtime

	def initialize_core_runtime_monitoring(self, runtime: WindowsCoreRuntime | None, log: Any) -> None:
		if runtime is None:
			return
		log.debug("Initializing watchdog")
		runtime.watchdog.initialize()

	def finalize_core_runtime_startup(self, runtime: WindowsCoreRuntime | None, log: Any) -> None:
		if runtime is None:
			return
		runtime.sessionTracking.initialize()

	def pump_core_runtime(
		self,
		runtime: WindowsCoreRuntime | None,
		*,
		queue_pump,
		braille_pump,
		vision_pump,
	) -> None:
		if runtime is None:
			queue_pump()
			braille_pump()
			vision_pump()
			return
		runtime.watchdog.alive()
		try:
			if runtime.touchHandler.handler:
				runtime.touchHandler.handler.pump()
			runtime.JABHandler.pumpAll()
			runtime.IAccessibleHandler.pumpAll()
			queue_pump()
			runtime.mouseHandler.pumpAll()
			braille_pump()
			vision_pump()
			runtime.sessionTracking.pumpAll()
		finally:
			runtime.watchdog.asleep()

	def cleanup_before_gui_exit(self, terminate) -> None:
		import watchdog

		# The core is expected to terminate, so we should not treat this as a crash.
		terminate(watchdog)

	def terminate_core_runtime(
		self,
		runtime: WindowsCoreRuntime | None,
		terminate,
		log: Any,
	) -> None:
		if runtime is None:
			return
		terminate(runtime.IAccessibleHandler, name="IAccessible support")
		terminate(runtime.UIAHandler, name="UIA support")
		terminate(runtime.winConsoleHandler, name="Legacy winConsole support")
		terminate(runtime.JABHandler, name="Java Access Bridge support")
		terminate(runtime.touchHandler)
		terminate(runtime.keyboardHandler, name="keyboard handler")
		terminate(runtime.mouseHandler)
		terminate(runtime.inputCore)
