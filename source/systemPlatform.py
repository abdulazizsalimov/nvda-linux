# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from functools import lru_cache
import sys

from systemPlatforms import UnsupportedPlatform
from systemPlatforms.base import SystemPlatform


@lru_cache(maxsize=1)
def getPlatform() -> SystemPlatform:
	if sys.platform == "win32":
		from systemPlatforms.windows import WindowsPlatform

		return WindowsPlatform()
	if sys.platform.startswith("linux"):
		from systemPlatforms.linux import LinuxPlatform

		return LinuxPlatform()
	return UnsupportedPlatform(sys.platform)
