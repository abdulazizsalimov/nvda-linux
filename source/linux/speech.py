# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import shutil
import subprocess
import threading
import time
from typing import Any

from languageHandler import getLanguage, stripLocaleFromLangCode


def _normalizeVoiceName(language: str | None) -> str | None:
	if not language:
		return None
	language = language.replace("_", "-").lower()
	if language == "windows":
		return None
	return language


def _candidateVoiceNames() -> tuple[str, ...]:
	language = _normalizeVoiceName(getLanguage())
	if not language:
		return ()
	candidates = [language]
	baseLanguage = stripLocaleFromLangCode(language)
	if baseLanguage and baseLanguage not in candidates:
		candidates.append(baseLanguage)
	return tuple(candidates)


def _sanitizeUtterance(text: str) -> str:
	return " ".join(text.split())


def buildFocusAnnouncement(snapshot) -> str:
	import controlTypes

	parts: list[str] = []
	name = (snapshot.name or "").strip()
	if name:
		parts.append(name)
	if snapshot.role not in controlTypes.silentRolesOnFocus or not name:
		parts.append(snapshot.role.displayString)
	try:
		stateLabels = controlTypes.processAndLabelStates(
			snapshot.role,
			set(snapshot.states),
			controlTypes.OutputReason.FOCUS,
		)
	except Exception:
		stateLabels = [
			state.displayString
			for state in sorted(snapshot.states, key=lambda state: state.value)
			if state.name not in {"FOCUSED", "FOCUSABLE"}
		]
	parts.extend(stateLabels)
	if not name and snapshot.applicationName:
		parts.append(snapshot.applicationName)
	return _sanitizeUtterance(" ".join(part for part in parts if part))


@dataclass(frozen=True)
class EspeakRequest:
	text: str
	interrupt: bool = True


class EspeakSpeaker:
	def __init__(
		self,
		*,
		log: Any,
		rate: int = 220,
		pitch: int = 50,
		amplitude: int = 100,
	) -> None:
		self._log = log
		self._rate = rate
		self._pitch = pitch
		self._amplitude = amplitude
		self._binary = shutil.which("espeak-ng")
		self._voiceCandidates = _candidateVoiceNames()
		self._requests: Queue[EspeakRequest] = Queue()
		self._stopEvent = threading.Event()
		self._worker = threading.Thread(
			target=self._run,
			name="linuxEspeakSpeaker",
			daemon=True,
		)
		self._processLock = threading.Lock()
		self._currentProcess: subprocess.Popen[str] | None = None
		self._lastText = ""
		self._lastSpokenAt = 0.0

	@property
	def isAvailable(self) -> bool:
		return self._binary is not None

	def start(self) -> None:
		if not self.isAvailable:
			raise RuntimeError("espeak-ng is not available")
		self._worker.start()

	def terminate(self) -> None:
		self._stopEvent.set()
		self.cancel()
		self._requests.put_nowait(EspeakRequest(text="", interrupt=False))
		if self._worker.is_alive():
			self._worker.join(timeout=2.0)

	def speak(self, text: str, *, interrupt: bool = True) -> bool:
		text = _sanitizeUtterance(text)
		if not self.isAvailable or not text:
			return False
		now = time.monotonic()
		if text == self._lastText and now - self._lastSpokenAt < 0.75:
			return False
		if interrupt:
			self.cancel()
		self._lastText = text
		self._lastSpokenAt = now
		self._requests.put_nowait(EspeakRequest(text=text, interrupt=interrupt))
		return True

	def cancel(self) -> None:
		while True:
			try:
				self._requests.get_nowait()
			except Empty:
				break
		with self._processLock:
			process = self._currentProcess
		if process is None:
			return
		try:
			process.terminate()
		except ProcessLookupError:
			return
		except Exception:
			self._log.debug("Failed to terminate current espeak-ng process", exc_info=True)

	def _run(self) -> None:
		while not self._stopEvent.is_set():
			try:
				request = self._requests.get(timeout=0.1)
			except Empty:
				continue
			if not request.text:
				continue
			try:
				self._speakRequest(request)
			except Exception:
				self._log.debug("Linux espeak-ng request failed", exc_info=True)

	def _speakRequest(self, request: EspeakRequest) -> None:
		voiceCandidates = list(self._voiceCandidates) + [None]
		lastReturnCode = 0
		for voice in voiceCandidates:
			command = [
				self._binary,
				"-s",
				str(self._rate),
				"-p",
				str(self._pitch),
				"-a",
				str(self._amplitude),
				"-z",
			]
			if voice:
				command.extend(("-v", voice))
			command.append(request.text)
			process = subprocess.Popen(
				command,
				stdin=subprocess.DEVNULL,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
				text=True,
			)
			with self._processLock:
				self._currentProcess = process
			try:
				returnCode = process.wait()
			finally:
				with self._processLock:
					if self._currentProcess is process:
						self._currentProcess = None
			lastReturnCode = returnCode
			if returnCode == 0:
				return
			if returnCode == -15:
				return
		self._log.debug("espeak-ng exited with code %s for utterance %r", lastReturnCode, request.text)
