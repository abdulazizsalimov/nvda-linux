# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NautilusMenuShortcutRule:
	label: str
	keyshortcuts: tuple[str, ...]
	hasPopup: bool | None = None


_SELECTION_MENU_SHORTCUT_RULES = (
	# Based on Nautilus selection-menu labels from
	# src/resources/menu/nautilus-files-view-context-menus.ui and
	# action bindings in src/nautilus-files-view.c.
	NautilusMenuShortcutRule(label="Open", keyshortcuts=("Alt+o",), hasPopup=True),
	NautilusMenuShortcutRule(label="Compress…", keyshortcuts=("Alt+o",), hasPopup=False),
	NautilusMenuShortcutRule(label="Open With…", keyshortcuts=("Alt+w",)),
	NautilusMenuShortcutRule(label="Run as a Program", keyshortcuts=("Alt+r",)),
	NautilusMenuShortcutRule(label="Scripts", keyshortcuts=("Alt+s",), hasPopup=True),
	NautilusMenuShortcutRule(label="Cut", keyshortcuts=("Control+X Alt+t",), hasPopup=False),
	NautilusMenuShortcutRule(label="Copy", keyshortcuts=("Control+C Alt+c",), hasPopup=False),
	NautilusMenuShortcutRule(label="Rename…", keyshortcuts=("F2 Alt+m",), hasPopup=False),
	NautilusMenuShortcutRule(label="Move to Trash", keyshortcuts=("Delete Alt+v",), hasPopup=False),
	NautilusMenuShortcutRule(label="Delete Permanently…", keyshortcuts=("Shift+Delete Alt+d",), hasPopup=False),
	NautilusMenuShortcutRule(
		label="Open Item Location",
		keyshortcuts=("Control+Alt+O Alt+o",),
		hasPopup=False,
	),
	# Properties is exposed with multiple bindings in Nautilus.
	NautilusMenuShortcutRule(
		label="Properties",
		keyshortcuts=(
			"Control+I Alt+r",
			"Alt+Return Alt+r",
			"Control+I Alt+Return Alt+r",
			"Alt+Return Control+I Alt+r",
		),
		hasPopup=False,
	),
	# Submenu entries inside the Open submenu.
	NautilusMenuShortcutRule(
		label="Open in New Tab",
		keyshortcuts=("Control+Return Alt+t",),
		hasPopup=False,
	),
	NautilusMenuShortcutRule(
		label="Open in New Window",
		keyshortcuts=("Shift+Return Alt+w",),
		hasPopup=False,
	),
	NautilusMenuShortcutRule(
		label="Open",
		keyshortcuts=("Return Control+O", "Control+O Return"),
		hasPopup=False,
	),
)


def resolveNautilusMenuShortcutLabel(
	*,
	keyshortcuts: str | None,
	hasPopup: bool,
) -> str | None:
	if not keyshortcuts:
		return None
	for rule in _SELECTION_MENU_SHORTCUT_RULES:
		if keyshortcuts not in rule.keyshortcuts:
			continue
		if rule.hasPopup is not None and rule.hasPopup != hasPopup:
			continue
		return rule.label
	return None
