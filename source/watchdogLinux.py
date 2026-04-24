# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from typing import Any


MIN_CORE_ALIVE_TIMEOUT = 0.5
NORMAL_CORE_ALIVE_TIMEOUT = 10
isRunning = False
isAttemptingRecovery = False


def alive():
	return None


def asleep():
	return None


def isCoreAsleep():
	return False


def initialize():
	global isRunning
	isRunning = True


def terminate():
	global isRunning
	isRunning = False


class Suspender:
	"""Linux headless runtime currently has no freeze recovery to suspend."""

	def __enter__(self):
		asleep()
		return self

	def __exit__(self, excType, excValue, traceback):
		alive()
		return False


def cancellableExecute(func, *args, ccPumpMessages=True, **kwargs):
	del ccPumpMessages
	return func(*args, **kwargs)


def cancellableSendMessage(hwnd, msg, wParam, lParam, flags=0, timeout=60000):
	del hwnd, msg, wParam, lParam, flags, timeout
	raise RuntimeError("cancellableSendMessage is only available on Windows")


class WatchdogObserver:
	@property
	def isAttemptingRecovery(self) -> bool:
		return False
