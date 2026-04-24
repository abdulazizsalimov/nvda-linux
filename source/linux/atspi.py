# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AtspiProbeResult:
	available: bool
	details: str
	source: str
	desktopCount: int | None = None
	desktopName: str | None = None
	rootChildCount: int | None = None


def _getBundledTypelibDirs() -> list[str]:
	repoRoot = Path(__file__).resolve().parents[2]
	typelibRoot = repoRoot / "localRuntime" / "atspi" / "usr" / "lib"
	if not typelibRoot.is_dir():
		return []
	return sorted(
		str(path)
		for path in typelibRoot.glob("*/girepository-1.0")
		if path.is_dir()
	)


def _getTypelibSearchPath() -> list[str]:
	searchPath: list[str] = []
	envPath = os.environ.get("GI_TYPELIB_PATH", "")
	if envPath:
		searchPath.extend(path for path in envPath.split(os.pathsep) if path)
	for path in _getBundledTypelibDirs():
		if path not in searchPath:
			searchPath.append(path)
	return searchPath


def prepareAtspiTypelibPath() -> list[str]:
	searchPath = _getTypelibSearchPath()
	if searchPath:
		os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(searchPath)
	return searchPath


def importAtspi() -> Any:
	prepareAtspiTypelibPath()
	import gi

	gi.require_version("Atspi", "2.0")
	from gi.repository import Atspi

	return Atspi


@lru_cache(maxsize=1)
def probeAtspiSupport() -> AtspiProbeResult:
	try:
		import gi
	except ImportError as e:
		return AtspiProbeResult(
			available=False,
			details=f"PyGObject is not available: {e}",
			source="python",
		)

	searchPath = prepareAtspiTypelibPath()
	source = "bundled-typelib" if _getBundledTypelibDirs() else "system"
	try:
		gi.require_version("Atspi", "2.0")
		from gi.repository import Atspi
	except Exception as e:
		return AtspiProbeResult(
			available=False,
			details=(
				f"AT-SPI GI bindings are not available: {type(e).__name__}: {e}. "
				f"GI_TYPELIB_PATH={os.pathsep.join(searchPath) if searchPath else '<unset>'}"
			),
			source=source,
		)

	try:
		desktopCount = Atspi.get_desktop_count()
		desktop = Atspi.get_desktop(0) if desktopCount else None
		desktopName = desktop.get_name() if desktop else None
		rootChildCount = desktop.get_child_count() if desktop else None
	except Exception as e:
		return AtspiProbeResult(
			available=False,
			details=f"AT-SPI bindings imported, but desktop probe failed: {type(e).__name__}: {e}",
			source=source,
		)

	return AtspiProbeResult(
		available=True,
		details="AT-SPI GI bindings are available and desktop probe succeeded.",
		source=source,
		desktopCount=desktopCount,
		desktopName=desktopName,
		rootChildCount=rootChildCount,
	)
