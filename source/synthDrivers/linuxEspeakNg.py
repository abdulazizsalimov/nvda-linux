# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from collections import OrderedDict

from . import _espeak_linux as _espeak
from synthDriverHandler import SynthDriver, VoiceInfo


class SynthDriver(SynthDriver):
	name = "linuxEspeakNg"
	description = "eSpeak NG (Linux)"

	supportedSettings = (
		SynthDriver.VoiceSetting(),
		SynthDriver.VariantSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.PitchSetting(),
		SynthDriver.VolumeSetting(),
	)
	supportedCommands = frozenset()
	supportedNotifications = frozenset()

	@classmethod
	def check(cls):
		try:
			_espeak.initialize()
		except Exception:
			return False
		else:
			_espeak.terminate()
			return True

	def __init__(self):
		_espeak.initialize()
		self._variantDict = _espeak.getVariantDict()
		self.variant = "max"
		self.rate = 30
		self.pitch = 40
		self.volume = 100

	def speak(self, speechSequence):
		text = " ".join(str(item) for item in speechSequence if isinstance(item, str)).strip()
		if text:
			_espeak.speak(text)

	def cancel(self):
		_espeak.stop()

	def pause(self, switch):
		_espeak.pause(switch)

	def terminate(self):
		super().terminate()
		_espeak.terminate()

	def _getAvailableVoices(self):
		voices = OrderedDict()
		for voice in _espeak.getVoiceList():
			language = _espeak.decodeEspeakString(voice.languages[1:])
			name = _espeak.decodeEspeakString(voice.name)
			identifier = _espeak.decodeEspeakString(voice.identifier).lower()
			voices[identifier] = VoiceInfo(identifier, name, language)
		return voices

	def _get_voice(self):
		curVoice = _espeak.getCurrentVoice()
		if not curVoice:
			return ""
		return _espeak.decodeEspeakString(curVoice.identifier).lower()

	def _set_voice(self, identifier):
		if identifier:
			_espeak.setVoiceAndVariant(voice=identifier, variant=self._variant)

	def _get_variant(self):
		return self._variant

	def _set_variant(self, value):
		self._variant = value if value in self._variantDict else "max"
		_espeak.setVoiceAndVariant(variant=self._variant)

	def _getAvailableVariants(self):
		return OrderedDict((variantId, VoiceInfo(variantId, name)) for variantId, name in self._variantDict.items())

	def _get_rate(self):
		return self._paramToPercent(_espeak.getParameter(_espeak.espeakRATE, 1), _espeak.minRate, _espeak.maxRate)

	def _set_rate(self, rate):
		value = self._percentToParam(rate, _espeak.minRate, _espeak.maxRate)
		_espeak.setParameter(_espeak.espeakRATE, value, 0)

	def _get_pitch(self):
		return self._paramToPercent(_espeak.getParameter(_espeak.espeakPITCH, 1), _espeak.minPitch, _espeak.maxPitch)

	def _set_pitch(self, pitch):
		value = self._percentToParam(pitch, _espeak.minPitch, _espeak.maxPitch)
		_espeak.setParameter(_espeak.espeakPITCH, value, 0)

	def _get_volume(self):
		return _espeak.getParameter(_espeak.espeakVOLUME, 1)

	def _set_volume(self, volume):
		_espeak.setParameter(_espeak.espeakVOLUME, volume, 0)
