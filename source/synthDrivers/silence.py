# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2006-2021 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from collections import OrderedDict
import synthDriverHandler


class SynthDriver(synthDriverHandler.SynthDriver):
	"""A dummy synth driver used to disable speech in NVDA."""

	name = "silence"
	# Translators: Description for a speech synthesizer.
	try:
		description = _("No speech")
	except NameError:
		description = "No speech"

	@classmethod
	def check(cls):
		return True

	supportedSettings = frozenset()
	_availableVoices = OrderedDict({name: synthDriverHandler.VoiceInfo(name, description)})

	def speak(self, speechSequence):
		self.lastIndex = None
		for item in speechSequence:
			if hasattr(item, "index"):
				self.lastIndex = item.index

	def cancel(self):
		self.lastIndex = None

	def _get_voice(self):
		return self.name
