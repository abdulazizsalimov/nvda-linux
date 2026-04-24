# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import gettext
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable
from xml.etree import ElementTree


_MENU_RESOURCE_PATH = "/org/gnome/nautilus/menu/nautilus-files-view-context-menus.ui"
_SHORTCUTS_RESOURCE_PATH = "/org/gnome/nautilus/ui/shortcuts-dialog.ui"


@dataclass(frozen=True)
class NautilusSelectionMenuItem:
	label: str
	action: str | None
	mnemonic: str | None
	hasSubmenu: bool
	accelerators: tuple[str, ...]
	showInView: str | None = None
	showInMode: str | None = None


@dataclass(frozen=True)
class _MenuVisibilityContext:
	showInView: str | None = None
	showInMode: str | None = None


def _normalizeText(value: str | None) -> str | None:
	if not value:
		return None
	value = " ".join(str(value).split())
	return value or None


def _stripMnemonicMarkers(label: str | None) -> str | None:
	label = _normalizeText(label)
	if not label:
		return None
	label = label.replace("__", "\0")
	label = label.replace("_", "")
	label = label.replace("\0", "_")
	return label


def _extractMnemonicShortcut(label: str | None) -> str | None:
	label = _normalizeText(label)
	if not label:
		return None
	escaped = False
	for index, character in enumerate(label):
		if escaped:
			escaped = False
			continue
		if character != "_":
			continue
		if index + 1 >= len(label):
			break
		nextCharacter = label[index + 1]
		if nextCharacter == "_":
			escaped = True
			continue
		return f"Alt+{nextCharacter.casefold()}"
	return None


def _normalizeComparisonText(text: str | None) -> str:
	text = _stripMnemonicMarkers(text) or ""
	text = text.replace("…", "")
	text = text.replace("(", " ").replace(")", " ")
	text = text.replace("-", " ")
	text = text.casefold()
	return " ".join(text.split())


def _normalizeShortcutToken(token: str | None) -> str | None:
	token = _normalizeText(token)
	if not token:
		return None
	token = token.replace("<Primary>", "Control+")
	token = token.replace("<Ctrl>", "Control+")
	token = token.replace("<control>", "Control+")
	token = token.replace("<Shift>", "Shift+")
	token = token.replace("<shift>", "Shift+")
	token = token.replace("<Alt>", "Alt+")
	token = token.replace("<alt>", "Alt+")
	token = token.replace("<Super>", "Super+")
	token = token.replace("<super>", "Super+")
	token = token.replace("<Meta>", "Meta+")
	token = token.replace("<meta>", "Meta+")
	token = token.replace("<KP_", "<Keypad ")
	token = token.replace(">", "")
	token = token.replace("<", "")
	token = token.replace("Primary+", "Control+")
	token = token.replace("KP_", "Keypad ")
	return token


def _normalizeShortcutSequence(shortcuts: Iterable[str]) -> tuple[str, ...]:
	normalizedShortcuts: list[str] = []
	for shortcut in shortcuts:
		normalizedShortcut = _normalizeShortcutToken(shortcut)
		if normalizedShortcut and normalizedShortcut not in normalizedShortcuts:
			normalizedShortcuts.append(normalizedShortcut)
	return tuple(normalizedShortcuts)


def _getNautilusTranslator():
	return gettext.translation("nautilus", fallback=True)


def _translateNautilusLabel(text: str | None, *, context: str | None = None) -> str | None:
	text = _normalizeText(text)
	if not text:
		return None
	translator = _getNautilusTranslator()
	if context and hasattr(translator, "pgettext"):
		try:
			return _normalizeText(translator.pgettext(context, text))
		except Exception:
			pass
	try:
		return _normalizeText(translator.gettext(text))
	except Exception:
		return text


def _extractNautilusResource(resourcePath: str) -> str | None:
	nautilusBinary = shutil.which("nautilus")
	gresourceBinary = shutil.which("gresource")
	if not nautilusBinary or not gresourceBinary:
		return None
	try:
		result = subprocess.run(
			[gresourceBinary, "extract", nautilusBinary, resourcePath],
			check=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
			text=True,
			encoding="utf-8",
		)
	except Exception:
		return None
	return result.stdout


def _loadNautilusXmlResource(resourcePath: str, sourceFallback: Path | None = None) -> ElementTree.Element | None:
	xmlText = _extractNautilusResource(resourcePath)
	if not xmlText and sourceFallback is not None and sourceFallback.is_file():
		xmlText = sourceFallback.read_text(encoding="utf-8")
	if not xmlText:
		return None
	try:
		return ElementTree.fromstring(xmlText)
	except ElementTree.ParseError:
		return None


@lru_cache(maxsize=1)
def _getSelectionMenuXmlRoot() -> ElementTree.Element | None:
	return _loadNautilusXmlResource(
		_MENU_RESOURCE_PATH,
		sourceFallback=Path("/tmp/nautilus-src/src/resources/menu/nautilus-files-view-context-menus.ui"),
	)


@lru_cache(maxsize=1)
def _getShortcutsDialogXmlRoot() -> ElementTree.Element | None:
	return _loadNautilusXmlResource(
		_SHORTCUTS_RESOURCE_PATH,
		sourceFallback=Path("/tmp/nautilus-src/src/resources/ui/shortcuts-dialog.ui"),
	)


@lru_cache(maxsize=1)
def _getShortcutsDialogSourceText() -> str | None:
	sourcePath = Path("/tmp/nautilus-src/src/resources/ui/shortcuts-dialog.blp")
	if not sourcePath.is_file():
		return None
	return sourcePath.read_text(encoding="utf-8")


def _parseShortcutDialogBlp() -> dict[str, tuple[str, ...]]:
	sourceText = _getShortcutsDialogSourceText()
	if not sourceText:
		return {}
	shortcuts: dict[str, tuple[str, ...]] = {}
	titleMatches = list(
		re.finditer(
			r'title:\s*C_\("shortcuts dialog",\s*"([^"]+)"\);\s*(?:accelerator:\s*"([^"]+)";)?',
			sourceText,
		),
	)
	for match in titleMatches:
		title = _translateNautilusLabel(match.group(1), context="shortcuts dialog")
		acceleratorText = match.group(2)
		if not title or not acceleratorText:
			continue
		shortcuts[_normalizeComparisonText(title)] = _normalizeShortcutSequence(acceleratorText.split())
	return shortcuts


def _parseShortcutDialogXml() -> dict[str, tuple[str, ...]]:
	root = _getShortcutsDialogXmlRoot()
	if root is None:
		return _parseShortcutDialogBlp()
	shortcuts: dict[str, tuple[str, ...]] = {}
	for objectNode in root.iter():
		if objectNode.tag != "object":
			continue
		className = objectNode.attrib.get("class", "")
		if "ShortcutsItem" not in className:
			continue
		title = None
		context = None
		acceleratorText = None
		for propertyNode in objectNode.findall("property"):
			propertyName = propertyNode.attrib.get("name")
			if propertyName == "title":
				title = propertyNode.text
				context = propertyNode.attrib.get("context")
			elif propertyName == "accelerator":
				acceleratorText = propertyNode.text
		title = _translateNautilusLabel(title, context=context)
		if not title or not acceleratorText:
			continue
		shortcuts[_normalizeComparisonText(title)] = _normalizeShortcutSequence(acceleratorText.split())
	return shortcuts


def _iterSelectionMenuItems(
	node,
	*,
	visibilityContext: _MenuVisibilityContext | None = None,
) -> Iterable[tuple[ElementTree.Element, _MenuVisibilityContext]]:
	visibilityContext = visibilityContext or _MenuVisibilityContext()
	for child in node:
		if child.tag in ("item", "submenu"):
			yield child, visibilityContext
			for linkNode in child.findall("link"):
				if linkNode.attrib.get("name") == "submenu":
					yield from _iterSelectionMenuItems(
						linkNode,
						visibilityContext=visibilityContext,
					)
			for sectionNode in child.findall("section"):
				yield from _iterSelectionMenuItems(
					sectionNode,
					visibilityContext=visibilityContext,
				)
		elif child.tag == "section":
			showInView = visibilityContext.showInView
			showInMode = visibilityContext.showInMode
			for attributeNode in child.findall("attribute"):
				attributeName = attributeNode.attrib.get("name")
				if attributeName == "show-in-view":
					showInView = _normalizeText(attributeNode.text)
				elif attributeName == "show-in-mode":
					showInMode = _normalizeText(attributeNode.text)
			yield from _iterSelectionMenuItems(
				child,
				visibilityContext=_MenuVisibilityContext(
					showInView=showInView,
					showInMode=showInMode,
				),
			)


def _resolveMenuItemAccelerators(
	label: str | None,
	shortcutsByTitle: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
	if not label:
		return ()
	labelKey = _normalizeComparisonText(label)
	if not labelKey:
		return ()
	if labelKey in shortcutsByTitle:
		return shortcutsByTitle[labelKey]
	candidateAccelerators: list[tuple[int, tuple[str, ...]]] = []
	for titleKey, accelerators in shortcutsByTitle.items():
		if not accelerators:
			continue
		if titleKey.endswith(labelKey) or labelKey.endswith(titleKey):
			candidateAccelerators.append((abs(len(titleKey) - len(labelKey)), accelerators))
		elif labelKey in titleKey or titleKey in labelKey:
			candidateAccelerators.append((100 + abs(len(titleKey) - len(labelKey)), accelerators))
	if not candidateAccelerators:
		return ()
	candidateAccelerators.sort(key=lambda item: item[0])
	return candidateAccelerators[0][1]


@lru_cache(maxsize=1)
def _getSelectionMenuItems() -> tuple[NautilusSelectionMenuItem, ...]:
	root = _getSelectionMenuXmlRoot()
	if root is None:
		return ()
	shortcutsByTitle = _parseShortcutDialogXml()
	selectionMenuNode = None
	for menuNode in root.findall("menu"):
		if menuNode.attrib.get("id") == "selection-menu":
			selectionMenuNode = menuNode
			break
	if selectionMenuNode is None:
		return ()
	items: list[NautilusSelectionMenuItem] = []
	for itemNode, inheritedVisibility in _iterSelectionMenuItems(selectionMenuNode):
		label = None
		action = None
		showInView = inheritedVisibility.showInView
		showInMode = inheritedVisibility.showInMode
		for attributeNode in itemNode.findall("attribute"):
			attributeName = attributeNode.attrib.get("name")
			if attributeName == "label":
				label = _translateNautilusLabel(
					attributeNode.text,
					context=attributeNode.attrib.get("context"),
				)
			elif attributeName == "action":
				action = _normalizeText(attributeNode.text)
			elif attributeName == "show-in-view":
				showInView = _normalizeText(attributeNode.text)
			elif attributeName == "show-in-mode":
				showInMode = _normalizeText(attributeNode.text)
		hasSubmenu = (
			itemNode.tag == "submenu"
			or itemNode.find("link[@name='submenu']") is not None
		)
		items.append(
			NautilusSelectionMenuItem(
				label=_stripMnemonicMarkers(label) or "",
				action=action,
				mnemonic=_extractMnemonicShortcut(label),
				hasSubmenu=hasSubmenu,
				accelerators=_resolveMenuItemAccelerators(label, shortcutsByTitle),
				showInView=showInView,
				showInMode=showInMode,
			),
		)
	return tuple(items)


def _parseLiveKeyShortcuts(keyshortcuts: str | None) -> tuple[tuple[str, ...], str | None]:
	keyshortcuts = _normalizeText(keyshortcuts)
	if not keyshortcuts:
		return (), None
	tokens = _normalizeShortcutSequence(keyshortcuts.split())
	mnemonic = None
	accelerators: list[str] = []
	for token in tokens:
		if token.startswith("Alt+") and len(token) <= 5:
			mnemonic = token
			continue
		accelerators.append(token)
	return tuple(accelerators), mnemonic


def resolveNautilusMenuShortcutLabel(
	*,
	keyshortcuts: str | None,
	hasPopup: bool,
) -> str | None:
	liveAccelerators, liveMnemonic = _parseLiveKeyShortcuts(keyshortcuts)
	if not liveAccelerators and not liveMnemonic:
		return None
	candidates = [
		item
		for item in _getSelectionMenuItems()
		if item.label
		and item.hasSubmenu == hasPopup
		and item.showInView != "network"
	]
	if liveMnemonic:
		candidates = [item for item in candidates if item.mnemonic == liveMnemonic]
	if not candidates:
		return None
	if liveAccelerators:
		acceleratorMatches = [
			item
			for item in candidates
			if any(accelerator in liveAccelerators for accelerator in item.accelerators)
		]
		if len(acceleratorMatches) == 1:
			return acceleratorMatches[0].label
		if acceleratorMatches:
			candidates = acceleratorMatches
	if len(candidates) == 1:
		return candidates[0].label
	return None
