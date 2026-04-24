# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from queue import Empty, Queue
import os
import re
import shutil
import subprocess
import threading
from typing import Callable

from languageHandler import getLanguage, stripLocaleFromLangCode
from logHandler import log


minRate = 80
maxRate = 449
minPitch = 0
maxPitch = 99

espeakRATE = 1
espeakVOLUME = 2
espeakPITCH = 3
espeakRANGE = 4

_PARAM_DEFAULTS = {
	espeakRATE: 175,
	espeakVOLUME: 100,
	espeakPITCH: 50,
	espeakRANGE: 50,
}


@dataclass(eq=False)
class espeak_VOICE:
	name: bytes
	languages: bytes
	identifier: bytes
	gender: int = 1
	age: int = 0
	variant: int = 0
	xx1: int = 0
	score: int = 0
	spare: int = 0


_binary = shutil.which("espeak-ng")
_indexCallback: Callable[[int | None], None] | None = None
_requestQueue: Queue[str] | None = None
_stopEvent: threading.Event | None = None
_workerThread: threading.Thread | None = None
_processLock = threading.Lock()
_currentProcess: subprocess.Popen[str] | None = None
_voicesByIdentifier: OrderedDict[str, espeak_VOICE] | None = None
_currentVoiceIdentifier: str | None = None
_currentVariant = "max"
_parameters = dict(_PARAM_DEFAULTS)
_markPattern = re.compile(r'<mark\s+name="(\d+)"\s*/?>')


def decodeEspeakString(data: bytes | bytearray | memoryview | str | None) -> str:
	if data is None:
		return ""
	if isinstance(data, str):
		return data
	return bytes(data).decode("utf-8", errors="ignore")


def _normalizeLanguage(language: str | None) -> str | None:
	if not language:
		return None
	language = language.replace("_", "-").lower()
	return language


def _listVoices() -> OrderedDict[str, espeak_VOICE]:
	global _voicesByIdentifier
	if _voicesByIdentifier is not None:
		return _voicesByIdentifier
	voices: OrderedDict[str, espeak_VOICE] = OrderedDict()
	if _binary is None:
		_voicesByIdentifier = voices
		return voices
	try:
		output = subprocess.check_output([_binary, "--voices"], text=True, stderr=subprocess.DEVNULL)
	except Exception:
		log.debug("Failed to query espeak-ng voices", exc_info=True)
		_voicesByIdentifier = voices
		return voices
	for line in output.splitlines()[1:]:
		parts = re.split(r"\s{2,}", line.strip(), maxsplit=4)
		if len(parts) < 5:
			continue
		priorityText, language, _ageGender, voiceName, identifier = parts[:5]
		try:
			priority = int(priorityText)
		except ValueError:
			priority = 5
		language = _normalizeLanguage(language) or language.lower()
		identifier = os.path.basename(identifier).lower()
		voices[identifier] = espeak_VOICE(
			name=voiceName.encode("utf-8"),
			languages=bytes((priority,)) + language.encode("utf-8"),
			identifier=identifier.encode("utf-8"),
			score=priority,
		)
	_voicesByIdentifier = voices
	return voices


def _voiceMatchesLanguage(voice: espeak_VOICE, language: str) -> bool:
	voiceLanguage = decodeEspeakString(voice.languages[1:])
	if not voiceLanguage:
		return False
	return voiceLanguage == language or stripLocaleFromLangCode(voiceLanguage) == stripLocaleFromLangCode(language)


def _getVoiceByLanguage(language: str | None) -> espeak_VOICE | None:
	language = _normalizeLanguage(language)
	if not language:
		return None
	voices = _listVoices()
	for voice in voices.values():
		if _voiceMatchesLanguage(voice, language):
			return voice
	baseLanguage = stripLocaleFromLangCode(language)
	if baseLanguage:
		for voice in voices.values():
			if _voiceMatchesLanguage(voice, baseLanguage):
				return voice
	return None


def _getCurrentVoiceIdentifier() -> str:
	global _currentVoiceIdentifier
	if _currentVoiceIdentifier:
		return _currentVoiceIdentifier
	voice = _getVoiceByLanguage(getLanguage())
	if voice is None:
		voices = _listVoices()
		if not voices:
			return "en"
		voice = next(iter(voices.values()))
	_currentVoiceIdentifier = decodeEspeakString(voice.identifier).lower()
	return _currentVoiceIdentifier


def _buildVoiceArgument() -> str:
	voiceIdentifier = _getCurrentVoiceIdentifier()
	if _currentVariant and _currentVariant != "none":
		return f"{voiceIdentifier}+{_currentVariant}"
	return voiceIdentifier


def _variantDirectories() -> tuple[str, ...]:
	return (
		"/usr/lib/x86_64-linux-gnu/espeak-ng-data/voices/!v",
		"/usr/lib/espeak-ng-data/voices/!v",
		"/usr/share/espeak-ng-data/voices/!v",
	)


def _extractVariantName(path: str) -> str | None:
	try:
		with open(path, "r", encoding="latin-1") as variantFile:
			for line in variantFile:
				if line.startswith("name "):
					parts = line.split(" ", 1)
					return parts[1].strip() if len(parts) == 2 else None
	except Exception:
		log.debug("Couldn't parse espeak variant file %s", path, exc_info=True)
	return None


def getVariantDict():
	variantDict = {"none": "none"}
	for variantDir in _variantDirectories():
		if not os.path.isdir(variantDir):
			continue
		for fileName in sorted(os.listdir(variantDir)):
			absFilePath = os.path.join(variantDir, fileName)
			if not os.path.isfile(absFilePath):
				continue
			variantName = _extractVariantName(absFilePath)
			if variantName:
				variantDict[fileName] = variantName
		break
	return variantDict


def _notifyIndexesForText(text: str) -> None:
	if _indexCallback is None:
		return
	for indexText in _markPattern.findall(text):
		try:
			_indexCallback(int(indexText))
		except Exception:
			log.debug("Failed to notify espeak-ng mark %s", indexText, exc_info=True)
	try:
		_indexCallback(None)
	except Exception:
		log.debug("Failed to notify espeak-ng completion", exc_info=True)


def _runWorker():
	global _currentProcess
	assert _requestQueue is not None
	assert _stopEvent is not None
	while not _stopEvent.is_set():
		try:
			text = _requestQueue.get(timeout=0.1)
		except Empty:
			continue
		if not text:
			continue
		if _binary is None:
			continue
		command = [
			_binary,
			"-m",
			"-s",
			str(_parameters[espeakRATE]),
			"-p",
			str(_parameters[espeakPITCH]),
			"-a",
			str(_parameters[espeakVOLUME]),
			"-v",
			_buildVoiceArgument(),
			"--stdin",
		]
		try:
			process = subprocess.Popen(
				command,
				stdin=subprocess.PIPE,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
				text=True,
			)
		except Exception:
			log.debug("Failed to start espeak-ng synth process", exc_info=True)
			continue
		with _processLock:
			_currentProcess = process
		try:
			process.communicate(text)
		except Exception:
			log.debug("espeak-ng synth process failed", exc_info=True)
		finally:
			with _processLock:
				if _currentProcess is process:
					_currentProcess = None
		if process.returncode == 0:
			_notifyIndexesForText(text)


def initialize(indexCallback=None):
	global _indexCallback, _requestQueue, _stopEvent, _workerThread, _voicesByIdentifier, _parameters
	if _binary is None:
		raise RuntimeError("espeak-ng is not available")
	_indexCallback = indexCallback
	_parameters = dict(_PARAM_DEFAULTS)
	_voicesByIdentifier = None
	_listVoices()
	_requestQueue = Queue()
	_stopEvent = threading.Event()
	_workerThread = threading.Thread(
		target=_runWorker,
		name=f"{__name__}.worker",
		daemon=True,
	)
	_workerThread.start()
	setVoiceByLanguage(getLanguage())


def terminate():
	global _workerThread, _requestQueue, _stopEvent, _currentProcess
	stop()
	if _stopEvent is not None:
		_stopEvent.set()
	if _requestQueue is not None:
		_requestQueue.put_nowait("")
	if _workerThread is not None and _workerThread.is_alive():
		_workerThread.join(timeout=2.0)
	_workerThread = None
	_requestQueue = None
	_stopEvent = None
	with _processLock:
		_currentProcess = None


def info():
	if _binary is None:
		return "unknown"
	try:
		output = subprocess.check_output([_binary, "--version"], text=True, stderr=subprocess.DEVNULL)
	except Exception:
		log.debug("Failed to query espeak-ng version", exc_info=True)
		return "unknown"
	return output.splitlines()[0].strip()


def speak(text):
	if _requestQueue is None or not text:
		return
	_requestQueue.put_nowait(text)


def stop():
	assert _requestQueue is None or _requestQueue is not None
	if _requestQueue is not None:
		while True:
			try:
				_requestQueue.get_nowait()
			except Empty:
				break
	with _processLock:
		process = _currentProcess
	if process is None:
		return
	try:
		process.terminate()
	except Exception:
		log.debug("Failed to terminate espeak-ng synth process", exc_info=True)


def pause(switch):
	if switch:
		stop()


def setParameter(param, value, relative):
	if relative:
		_parameters[param] = _parameters.get(param, _PARAM_DEFAULTS.get(param, 0)) + value
	else:
		_parameters[param] = value


def getParameter(param, current):
	del current
	return _parameters.get(param, _PARAM_DEFAULTS.get(param, 0))


def getVoiceList():
	return list(_listVoices().values())


def getCurrentVoice():
	return _listVoices().get(_getCurrentVoiceIdentifier())


def setVoice(voice):
	setVoiceByName(decodeEspeakString(voice.identifier))


def setVoiceByName(name):
	global _currentVoiceIdentifier
	name = decodeEspeakString(name).lower()
	voices = _listVoices()
	if name in voices:
		_currentVoiceIdentifier = name
		return
	baseName = os.path.basename(name).lower()
	if baseName in voices:
		_currentVoiceIdentifier = baseName
		return
	raise LookupError(f"Unknown espeak-ng voice {name!r}")


def setVoiceByLanguage(lang):
	global _currentVoiceIdentifier
	voice = _getVoiceByLanguage(lang)
	if voice is None:
		return
	_currentVoiceIdentifier = decodeEspeakString(voice.identifier).lower()


def setVoiceAndVariant(voice=None, variant=None):
	global _currentVariant
	if voice:
		setVoiceByName(voice)
	if variant is not None:
		_currentVariant = variant
