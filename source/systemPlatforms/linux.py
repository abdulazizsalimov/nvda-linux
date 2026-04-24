# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import tempfile
import threading
import time
from typing import Any

from linux.accessibility import (
	AtspiFocusEventMonitor,
	DesktopSnapshot,
	clearAccessibleCache,
	describeObjectSnapshot,
	describeAccessibleNameSources,
	replaceObjectSnapshotName,
	resolveAccessibleObjectSnapshot,
	snapshotDesktop,
)
from linux.presentation import (
	LinuxDefaultScript,
	LinuxFocusManager,
	LinuxGtkScript,
	LinuxPresentationManager,
	LinuxSpeechGenerator,
)
from linux.speech import EspeakSpeaker
from linux.atspi import probeAtspiSupport
from .base import SystemPlatform


@dataclass
class LinuxInstanceMutex:
	lockFile: Any
	path: str


@dataclass
class LinuxBootstrapRuntime:
	desktopSnapshot: DesktopSnapshot | None = None
	focusEventMonitor: AtspiFocusEventMonitor | None = None


@dataclass
class LinuxCoreRuntime:
	focusEventMonitor: AtspiFocusEventMonitor | None = None
	glibMainContext: Any | None = None
	pollIntervalSeconds: float = 0.05
	interrupted: bool = False
	speaker: EspeakSpeaker | None = None
	focusManager: LinuxFocusManager | None = None
	speechGenerator: LinuxSpeechGenerator | None = None
	presentationManager: LinuxPresentationManager | None = None
	defaultScript: LinuxDefaultScript | None = None
	lastAnnouncementKey: tuple[str, str | None] | None = None
	lastAnnouncementTime: float = 0.0
	lastPresentedSourceKey: int | None = None
	lastPresentedSourceTime: float = 0.0


class LinuxPlatform(SystemPlatform):
	name = "linux"

	def acquire_single_instance_mutex(
		self,
		desktop_name: str,
		logger,
	) -> LinuxInstanceMutex:
		import fcntl

		lockPath = os.path.join(tempfile.gettempdir(), f"nvda-{desktop_name}.lock")
		lockFile = open(lockPath, "a+", encoding="utf-8")
		try:
			fcntl.flock(lockFile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
		except BlockingIOError as e:
			lockFile.close()
			raise RuntimeError(f"Another NVDA instance appears to be running (lock: {lockPath})") from e
		logger.debug(f"Acquired Linux instance lock: {lockPath}")
		return LinuxInstanceMutex(lockFile=lockFile, path=lockPath)

	def release_single_instance_mutex(self, mutex: object, log: Any) -> None:
		if not isinstance(mutex, LinuxInstanceMutex):
			return
		import fcntl

		try:
			fcntl.flock(mutex.lockFile.fileno(), fcntl.LOCK_UN)
		except OSError:
			log.debug(f"Failed to unlock Linux instance lock: {mutex.path}", exc_info=True)
		try:
			mutex.lockFile.close()
		except OSError:
			log.debug(f"Failed to close Linux instance lock: {mutex.path}", exc_info=True)

	def is_runtime_supported(self) -> bool:
		return probeAtspiSupport().available

	def initialize_platform_bootstrap_runtime(
		self,
		*,
		app_args: Any,
		config: Any,
		app_dir: str,
		log: Any,
	) -> LinuxBootstrapRuntime | None:
		del app_args, config, app_dir
		atspiProbe = probeAtspiSupport()
		if not atspiProbe.available:
			log.info("Linux AT-SPI bootstrap runtime unavailable: %s", atspiProbe.details)
			return None
		runtime = LinuxBootstrapRuntime()
		try:
			runtime.desktopSnapshot = snapshotDesktop()
		except Exception:
			log.debug("Failed to snapshot Linux AT-SPI desktop during bootstrap", exc_info=True)
		try:
			runtime.focusEventMonitor = AtspiFocusEventMonitor()
			registeredEvents = runtime.focusEventMonitor.register()
		except Exception:
			log.debug("Failed to register Linux AT-SPI presentation event monitor", exc_info=True)
			runtime.focusEventMonitor = None
		else:
			log.info("Linux AT-SPI presentation event monitor registered: %s", registeredEvents)
		return runtime

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
		del terminate, app_args, config, app_dir, log
		if not isinstance(runtime, LinuxBootstrapRuntime):
			return
		if runtime.focusEventMonitor is not None:
			runtime.focusEventMonitor.deregister()

	def log_runtime_info(self, log: Any) -> None:
		atspiProbe = probeAtspiSupport()
		log.info(f"Platform: {os.sys.platform}")
		log.info(
			"Linux AT-SPI probe: available=%s source=%s desktopCount=%s desktopName=%s rootChildCount=%s",
			atspiProbe.available,
			atspiProbe.source,
			atspiProbe.desktopCount,
			atspiProbe.desktopName,
			atspiProbe.rootChildCount,
		)
		if atspiProbe.available:
			try:
				desktop = snapshotDesktop()
			except Exception:
				log.debug("Failed to snapshot Linux AT-SPI desktop", exc_info=True)
			else:
				log.info(
					"Linux AT-SPI desktop snapshot: applications=%s normalizedApplications=%s",
					[
						f"{app.role}:{app.name}:{app.childCount}"
						for app in desktop.applications
					],
					[
						describeObjectSnapshot(app)
						for app in desktop.normalizedApplications
					],
				)

	def uses_headless_core_runtime(self) -> bool:
		return self.is_runtime_supported()

	def initialize_core_runtime(
		self,
		*,
		bootstrap_runtime: object | None,
		log: Any,
	) -> LinuxCoreRuntime:
		focusEventMonitor = None
		if isinstance(bootstrap_runtime, LinuxBootstrapRuntime):
			focusEventMonitor = bootstrap_runtime.focusEventMonitor
		if focusEventMonitor is None and probeAtspiSupport().available:
			try:
				focusEventMonitor = AtspiFocusEventMonitor()
				registeredEvents = focusEventMonitor.register()
			except Exception:
				log.debug(
					"Failed to create Linux AT-SPI presentation event monitor for core runtime",
					exc_info=True,
				)
				focusEventMonitor = None
			else:
				log.info("Linux AT-SPI core presentation event monitor registered: %s", registeredEvents)
		try:
			from gi.repository import GLib
		except Exception:
			log.debug("Unable to import GLib for Linux headless runtime", exc_info=True)
			glibMainContext = None
		else:
			glibMainContext = GLib.MainContext.default()
		runtime = LinuxCoreRuntime(
			focusEventMonitor=focusEventMonitor,
			glibMainContext=glibMainContext,
		)
		runtime.focusManager = LinuxFocusManager()
		runtime.speechGenerator = LinuxSpeechGenerator()
		runtime.presentationManager = LinuxPresentationManager(
			focusManager=runtime.focusManager,
			speechGenerator=runtime.speechGenerator,
		)
		runtime.defaultScript = LinuxGtkScript(
			focusManager=runtime.focusManager,
			presentationManager=runtime.presentationManager,
		)
		try:
			speaker = EspeakSpeaker(log=log)
		except Exception:
			log.debug("Failed to construct Linux espeak-ng speaker", exc_info=True)
		else:
			if speaker.isAvailable:
				try:
					speaker.start()
				except Exception:
					log.debug("Failed to start Linux espeak-ng speaker", exc_info=True)
				else:
					runtime.speaker = speaker
					log.info("Linux speech backend initialized with espeak-ng")
			else:
				log.info("Linux speech backend unavailable: espeak-ng was not found")
		return runtime

	def run_headless_core_loop(self, runtime: object | None, log: Any) -> None:
		if not isinstance(runtime, LinuxCoreRuntime):
			return
		log.info(
			"Linux headless runtime active; waiting for AT-SPI focus events. Press Ctrl+C to exit.",
		)
		if runtime.speaker is not None:
			runtime.speaker.speak("NVDA Linux runtime active")
		originalSigintHandler, originalSigtermHandler = self._installSignalHandlers(runtime, log)
		try:
			while not runtime.interrupted:
				contextActivity = self._pumpGlibMainContext(runtime.glibMainContext, log)
				eventActivity = self._drainFocusEvents(runtime, log)
				if not contextActivity and not eventActivity:
					time.sleep(runtime.pollIntervalSeconds)
		finally:
			self._restoreSignalHandlers(originalSigintHandler, originalSigtermHandler)

	def _installSignalHandlers(self, runtime: LinuxCoreRuntime, log: Any) -> tuple[Any, Any]:
		if threading.current_thread() is not threading.main_thread():
			return None, None
		originalSigintHandler = signal.getsignal(signal.SIGINT)
		originalSigtermHandler = signal.getsignal(signal.SIGTERM)

		def _handleTerminationSignal(signum, frame) -> None:
			del frame
			runtime.interrupted = True
			log.debug("Linux headless runtime received signal %s", signum)

		signal.signal(signal.SIGINT, _handleTerminationSignal)
		signal.signal(signal.SIGTERM, _handleTerminationSignal)
		return originalSigintHandler, originalSigtermHandler

	def _restoreSignalHandlers(self, originalSigintHandler: Any, originalSigtermHandler: Any) -> None:
		if threading.current_thread() is not threading.main_thread():
			return
		if originalSigintHandler is not None:
			signal.signal(signal.SIGINT, originalSigintHandler)
		if originalSigtermHandler is not None:
			signal.signal(signal.SIGTERM, originalSigtermHandler)

	def _pumpGlibMainContext(self, glibMainContext: Any | None, log: Any) -> bool:
		if glibMainContext is None:
			return False
		hadActivity = False
		while True:
			try:
				if not glibMainContext.pending():
					break
				hadActivity = bool(glibMainContext.iteration(False)) or hadActivity
			except Exception:
				log.debug("Failed while pumping GLib main context", exc_info=True)
				return hadActivity
		try:
			hadActivity = bool(glibMainContext.iteration(False)) or hadActivity
		except Exception:
			log.debug("Failed to iterate GLib main context", exc_info=True)
		return hadActivity

	def _drainFocusEvents(self, runtime: LinuxCoreRuntime, log: Any) -> bool:
		focusEventMonitor = runtime.focusEventMonitor
		if focusEventMonitor is None:
			return False
		pendingEvents = focusEventMonitor.drainPendingEvents()
		if not pendingEvents:
			return False
		for event in pendingEvents:
			if event.eventType.startswith("object:attributes-changed") and event.sourceAccessible is not None:
				try:
					clearAccessibleCache(event.sourceAccessible)
				except Exception:
					log.debug("Failed to refresh AT-SPI object after attributes-changed", exc_info=True)
			if event.sourceObject is not None:
				log.info(
					"Linux AT-SPI %s: %s",
					event.eventLabel,
					describeObjectSnapshot(event.sourceObject),
				)
			else:
				log.info(
					"Linux AT-SPI %s: role=%s name=%r app=%r",
					event.eventLabel,
					event.sourceRole,
					event.sourceName,
					event.hostApplicationName,
				)
			if event.debugNameSources:
				log.info(
					"Linux AT-SPI %s name sources: %s",
					event.eventLabel,
					event.debugNameSources,
				)
			presentationResult = None
			if event.shouldAnnounce and runtime.defaultScript is not None:
				presentationResult = runtime.defaultScript.handle_event(
					event,
					resolveSnapshot=lambda currentEvent: self._resolvePresentationSnapshot(
						currentEvent,
						focusEventMonitor=focusEventMonitor,
						glibMainContext=runtime.glibMainContext,
						log=log,
					),
				)
			if (
				presentationResult is not None
				and runtime.speaker is not None
				and presentationResult.snapshot is not None
				and self._shouldSpeakAnnouncement(
					runtime,
					presentationResult.announcement,
					presentationResult.snapshot,
					event=event,
				)
			):
				runtime.speaker.speak(
					presentationResult.announcement,
					interrupt=presentationResult.interrupt,
				)
		return True

	def _shouldSpeakAnnouncement(
		self,
		runtime: LinuxCoreRuntime,
		announcement: str,
		resolvedObject,
		event,
		dedupWindowSeconds: float = 0.2,
		sameObjectBurstWindowSeconds: float = 0.45,
	) -> bool:
		now = time.monotonic()
		sourceAccessible = getattr(event, "sourceAccessible", None)
		sourceKey = hash(sourceAccessible) if sourceAccessible is not None else None
		if (
			sourceKey is not None
			and sourceKey == runtime.lastPresentedSourceKey
			and now - runtime.lastPresentedSourceTime <= sameObjectBurstWindowSeconds
			and not event.eventType.startswith("object:property-change:accessible-name")
		):
			return False
		announcementKey = (
			announcement,
			resolvedObject.applicationName,
		)
		if (
			announcementKey == runtime.lastAnnouncementKey
			and now - runtime.lastAnnouncementTime <= dedupWindowSeconds
		):
			return False
		runtime.lastPresentedSourceKey = sourceKey
		runtime.lastPresentedSourceTime = now
		runtime.lastAnnouncementKey = announcementKey
		runtime.lastAnnouncementTime = now
		return True

	def _resolvePresentationSnapshot(
		self,
		event,
		*,
		focusEventMonitor: AtspiFocusEventMonitor,
		glibMainContext: Any | None,
		log: Any,
	):
		if event.sourceObject is None:
			return None
		resolvedObject = event.sourceObject
		if event.sourceObject.name is None and event.sourceAccessible is not None:
			resolvedObject = self._lateResolveFocusedObject(
				event=event,
				focusEventMonitor=focusEventMonitor,
				glibMainContext=glibMainContext,
				log=log,
			) or resolvedObject
		if event.nameOverride and event.nameOverride != resolvedObject.name:
			log.info(
				"Linux AT-SPI name-change override: role=%s name=%r app=%r",
				resolvedObject.roleName,
				event.nameOverride,
				resolvedObject.applicationName,
			)
			resolvedObject = replaceObjectSnapshotName(resolvedObject, event.nameOverride)
		return resolvedObject

	def _lateResolveFocusedObject(
		self,
		*,
		event,
		focusEventMonitor: AtspiFocusEventMonitor,
		glibMainContext: Any | None,
		log: Any,
	):
		sourceAccessible = event.sourceAccessible
		if sourceAccessible is None:
			return event.sourceObject
		resolvedObject = resolveAccessibleObjectSnapshot(
			sourceAccessible,
			attempts=8,
			delaySeconds=0.02,
			settleCallback=lambda: self._pumpLateResolutionMainContext(
				glibMainContext,
				log,
			),
			shouldContinue=lambda: focusEventMonitor.latestFocusedAccessible is sourceAccessible,
		)
		if resolvedObject is None:
			return event.sourceObject
		if resolvedObject.name and resolvedObject.name != event.sourceObject.name:
			log.info(
				"Linux AT-SPI late-resolved focus: %s",
				describeObjectSnapshot(resolvedObject),
			)
			return resolvedObject
		if resolvedObject.name is None and resolvedObject.childCount > 0:
			log.info(
				"Linux AT-SPI object still nameless after raw resolution; "
				"continuing with live accessible presentation",
			)
		if resolvedObject.name is None and resolvedObject.childCount > 0:
			try:
				log.info(
					"Linux AT-SPI late name sources: %s",
					describeAccessibleNameSources(sourceAccessible),
				)
			except Exception:
				log.debug("Failed to describe late AT-SPI name sources", exc_info=True)
		return resolvedObject


	def _pumpLateResolutionMainContext(self, glibMainContext: Any | None, log: Any) -> None:
		if glibMainContext is None:
			return
		deadline = time.monotonic() + 0.03
		while time.monotonic() < deadline:
			hadActivity = self._pumpGlibMainContext(glibMainContext, log)
			if not hadActivity:
				time.sleep(0.005)

	def terminate_core_runtime(
		self,
		runtime: object | None,
		terminate,
		log: Any,
	) -> None:
		del terminate, log
		if not isinstance(runtime, LinuxCoreRuntime):
			return
		if runtime.speaker is not None:
			runtime.speaker.terminate()

	def get_runtime_unsupported_message(self) -> str:
		atspiProbe = probeAtspiSupport()
		atspiMessage = (
			f"{atspiProbe.details} "
			f"(source={atspiProbe.source}, desktopCount={atspiProbe.desktopCount}, "
			f"desktopName={atspiProbe.desktopName}, rootChildCount={atspiProbe.rootChildCount})"
		)
		return (
			"Linux/GNOME runtime requires AT-SPI to be available before headless testing can start. "
			"Launcher, args, config, logging, instance detection, desktop/session bootstrap, "
			"single-instance coordination, early core config/language bootstrap, and AT-SPI probing "
			"are already platform-safe. "
			f"AT-SPI probe: {atspiMessage}"
		)
