# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2008-2025 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import sys


if sys.platform == "win32":
	from watchdogWindows import *  # noqa: F401,F403
else:
	from watchdogLinux import *  # noqa: F401,F403
