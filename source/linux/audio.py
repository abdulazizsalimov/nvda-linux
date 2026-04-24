# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from ctypes import (
	Structure,
	byref,
	c_char_p,
	c_int,
	c_long,
	c_size_t,
	c_uint32,
	c_uint8,
	c_void_p,
	create_string_buffer,
	string_at,
)
from ctypes.util import find_library
import threading

from logHandler import log


PA_STREAM_PLAYBACK = 1
PA_SAMPLE_S16LE = 3

SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_ACCESS_RW_INTERLEAVED = 3
SND_PCM_FORMAT_S16_LE = 2


class pa_sample_spec(Structure):
	_fields_ = (
		("format", c_int),
		("rate", c_uint32),
		("channels", c_uint8),
	)


class _PulseAudioBackend:
	def __init__(self, *, channels: int, samplesPerSec: int, bitsPerSample: int, streamName: str):
		if bitsPerSample != 16:
			raise ValueError("PulseAudio backend currently supports 16-bit PCM only")
		libraryName = find_library("pulse-simple")
		if not libraryName:
			raise OSError("Unable to locate libpulse-simple")
		self._pulse = __import__("ctypes").cdll.LoadLibrary(libraryName)
		self._pulse.pa_simple_new.restype = c_void_p
		self._pulse.pa_simple_new.argtypes = (
			c_char_p,
			c_char_p,
			c_int,
			c_char_p,
			c_char_p,
			c_void_p,
			c_void_p,
			c_void_p,
			c_void_p,
		)
		self._pulse.pa_simple_write.argtypes = (c_void_p, c_void_p, c_size_t, c_void_p)
		self._pulse.pa_simple_drain.argtypes = (c_void_p, c_void_p)
		self._pulse.pa_simple_flush.argtypes = (c_void_p, c_void_p)
		self._pulse.pa_simple_free.argtypes = (c_void_p,)
		self.channels = channels
		self.samplesPerSec = samplesPerSec
		self.bitsPerSample = bitsPerSample
		self._streamName = streamName.encode("utf-8")
		self._sampleSpec = pa_sample_spec(
			format=PA_SAMPLE_S16LE,
			rate=samplesPerSec,
			channels=channels,
		)
		self._simple: int | None = None

	def _ensureConnected(self) -> None:
		if self._simple is not None:
			return
		err = c_int()
		simple = self._pulse.pa_simple_new(
			None,
			b"NVDA",
			PA_STREAM_PLAYBACK,
			None,
			self._streamName,
			byref(self._sampleSpec),
			None,
			None,
			byref(err),
		)
		if not simple:
			raise OSError(f"Failed to connect to PulseAudio, error={err.value}")
		self._simple = simple

	def feed(self, payload: bytes, *, onDone=None) -> None:
		self._ensureConnected()
		buf = create_string_buffer(payload)
		err = c_int()
		res = self._pulse.pa_simple_write(self._simple, buf, len(payload), byref(err))
		if res < 0:
			raise OSError(f"PulseAudio write failed, error={err.value}")
		if onDone is not None:
			onDone()

	def idle(self) -> None:
		if self._simple is None:
			return
		err = c_int()
		res = self._pulse.pa_simple_drain(self._simple, byref(err))
		if res < 0:
			raise OSError(f"PulseAudio drain failed, error={err.value}")

	def stop(self) -> None:
		if self._simple is None:
			return
		err = c_int()
		res = self._pulse.pa_simple_flush(self._simple, byref(err))
		if res < 0:
			raise OSError(f"PulseAudio flush failed, error={err.value}")

	def close(self) -> None:
		if self._simple is None:
			return
		self._pulse.pa_simple_free(self._simple)
		self._simple = None


class _AlsaBackend:
	def __init__(self, *, channels: int, samplesPerSec: int, bitsPerSample: int):
		if bitsPerSample != 16:
			raise ValueError("ALSA backend currently supports 16-bit PCM only")
		libraryName = find_library("asound")
		if not libraryName:
			raise OSError("Unable to locate libasound")
		self._alsa = __import__("ctypes").cdll.LoadLibrary(libraryName)
		self._alsa.snd_pcm_open.argtypes = (c_void_p, c_char_p, c_int, c_int)
		self._alsa.snd_pcm_set_params.argtypes = (c_void_p, c_int, c_int, c_uint32, c_uint32, c_int, c_uint32)
		self._alsa.snd_pcm_writei.argtypes = (c_void_p, c_void_p, c_long)
		self._alsa.snd_pcm_prepare.argtypes = (c_void_p,)
		self._alsa.snd_pcm_drain.argtypes = (c_void_p,)
		self._alsa.snd_pcm_drop.argtypes = (c_void_p,)
		self._alsa.snd_pcm_close.argtypes = (c_void_p,)
		self._alsa.snd_strerror.restype = c_char_p
		self.channels = channels
		self.samplesPerSec = samplesPerSec
		self.bitsPerSample = bitsPerSample
		self._pcm = c_void_p()

	def _errorText(self, code: int) -> str:
		try:
			text = self._alsa.snd_strerror(code)
			if text:
				return text.decode("utf-8", errors="ignore")
		except Exception:
			pass
		return str(code)

	def _ensureConnected(self) -> None:
		if self._pcm.value:
			return
		res = self._alsa.snd_pcm_open(byref(self._pcm), b"default", SND_PCM_STREAM_PLAYBACK, 0)
		if res < 0:
			raise OSError(f"ALSA open failed: {self._errorText(res)}")
		res = self._alsa.snd_pcm_set_params(
			self._pcm,
			SND_PCM_FORMAT_S16_LE,
			SND_PCM_ACCESS_RW_INTERLEAVED,
			self.channels,
			self.samplesPerSec,
			1,
			500000,
		)
		if res < 0:
			self.close()
			raise OSError(f"ALSA set_params failed: {self._errorText(res)}")

	def feed(self, payload: bytes, *, onDone=None) -> None:
		self._ensureConnected()
		buf = create_string_buffer(payload)
		frameSize = (self.bitsPerSample // 8) * self.channels
		frameCount = len(payload) // frameSize
		res = self._alsa.snd_pcm_writei(self._pcm, buf, frameCount)
		if res < 0:
			self._alsa.snd_pcm_prepare(self._pcm)
			raise OSError(f"ALSA write failed: {self._errorText(res)}")
		if onDone is not None:
			onDone()

	def idle(self) -> None:
		if not self._pcm.value:
			return
		res = self._alsa.snd_pcm_drain(self._pcm)
		if res < 0:
			raise OSError(f"ALSA drain failed: {self._errorText(res)}")
		self._alsa.snd_pcm_prepare(self._pcm)

	def stop(self) -> None:
		if not self._pcm.value:
			return
		res = self._alsa.snd_pcm_drop(self._pcm)
		if res < 0:
			raise OSError(f"ALSA drop failed: {self._errorText(res)}")
		self._alsa.snd_pcm_prepare(self._pcm)

	def close(self) -> None:
		if not self._pcm.value:
			return
		self._alsa.snd_pcm_close(self._pcm)
		self._pcm = c_void_p()


class LinuxWavePlayer:
	def __init__(self, *, channels: int, samplesPerSec: int, bitsPerSample: int):
		self.channels = channels
		self.samplesPerSec = samplesPerSec
		self.bitsPerSample = bitsPerSample
		self._lock = threading.RLock()
		self._activeBackend = None
		self._backendFailureLogged = False
		self._backends = []
		try:
			self._backends.append(
				_PulseAudioBackend(
					channels=channels,
					samplesPerSec=samplesPerSec,
					bitsPerSample=bitsPerSample,
					streamName="NVDA Speech",
				),
			)
		except Exception:
			log.debug("PulseAudio backend unavailable for Linux speech", exc_info=True)
		try:
			self._backends.append(
				_AlsaBackend(
					channels=channels,
					samplesPerSec=samplesPerSec,
					bitsPerSample=bitsPerSample,
				),
			)
		except Exception:
			log.debug("ALSA backend unavailable for Linux speech", exc_info=True)

	def _ensureBackend(self):
		if self._activeBackend is not None:
			return self._activeBackend
		errors = []
		for backend in self._backends:
			try:
				backend._ensureConnected()
			except Exception as error:
				errors.append(str(error))
				continue
			self._activeBackend = backend
			self._backendFailureLogged = False
			log.info("Linux speech audio backend active: %s", backend.__class__.__name__)
			return backend
		if errors and not self._backendFailureLogged:
			self._backendFailureLogged = True
			log.debugWarning("Unable to initialize Linux speech audio backend: %s", " | ".join(errors))
		return None

	def feed(self, data, *, size: int, onDone=None):
		with self._lock:
			backend = self._ensureBackend()
			if backend is None:
				return
			payload = string_at(data, size)
			try:
				backend.feed(payload, onDone=onDone)
			except Exception:
				log.debug("Linux speech audio feed failed; dropping active backend", exc_info=True)
				self._activeBackend = None
				self._backendFailureLogged = False

	def idle(self):
		with self._lock:
			backend = self._activeBackend
			if backend is None:
				return
			try:
				backend.idle()
			except Exception:
				log.debug("Linux speech audio drain failed", exc_info=True)
				self._activeBackend = None
				self._backendFailureLogged = False

	def stop(self):
		with self._lock:
			backend = self._activeBackend
			if backend is None:
				return
			try:
				backend.stop()
			except Exception:
				log.debug("Linux speech audio stop failed", exc_info=True)
				self._activeBackend = None
				self._backendFailureLogged = False

	def pause(self, switch: bool):
		if switch:
			self.stop()

	def close(self):
		with self._lock:
			for backend in self._backends:
				try:
					backend.close()
				except Exception:
					log.debug("Linux speech audio backend close failed", exc_info=True)
			self._activeBackend = None
			self._backendFailureLogged = False


def createWavePlayer(*, channels: int, samplesPerSec: int, bitsPerSample: int) -> LinuxWavePlayer:
	return LinuxWavePlayer(
		channels=channels,
		samplesPerSec=samplesPerSec,
		bitsPerSample=bitsPerSample,
	)
