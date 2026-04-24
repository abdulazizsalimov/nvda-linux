# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import re
import shutil
import subprocess
import threading
import time
from typing import Any

from languageHandler import getLanguage, stripLocaleFromLangCode
from linux.atspi import importAtspi
from linux.accessibility import snapshotAccessibleObject


def _normalizeVoiceName(language: str | None) -> str | None:
	if not language:
		return None
	language = language.replace("_", "-").lower()
	if language == "windows":
		return None
	return language


def _candidateVoiceNames() -> tuple[str, ...]:
	language = _normalizeVoiceName(getLanguage())
	if not language:
		return ()
	candidates = [language]
	baseLanguage = stripLocaleFromLangCode(language)
	if baseLanguage and baseLanguage not in candidates:
		candidates.append(baseLanguage)
	return tuple(candidates)


def _sanitizeUtterance(text: str) -> str:
	return " ".join(text.split())


def _callAccessibleStringMethod(accessible, methodName: str) -> str | None:
	if accessible is None:
		return None
	method = getattr(accessible, methodName, None)
	if not callable(method):
		return None
	try:
		return _sanitizeUtterance(method() or "") or None
	except Exception:
		return None


def _getAccessibleSelfName(accessible, *, nameOverride: str | None = None) -> str | None:
	if nameOverride:
		return _sanitizeUtterance(nameOverride) or None
	return _callAccessibleStringMethod(accessible, "get_name")


def _getAccessibleDescription(accessible) -> str | None:
	return _callAccessibleStringMethod(accessible, "get_description")


def _getAccessibleTextContent(accessible) -> str | None:
	if accessible is None:
		return None
	textIface = None
	getTextIface = getattr(accessible, "get_text_iface", None)
	if callable(getTextIface):
		try:
			textIface = getTextIface()
		except Exception:
			textIface = None
	if textIface is None:
		isText = getattr(accessible, "is_text", None)
		try:
			if callable(isText) and isText():
				textIface = accessible
		except Exception:
			textIface = None
	if textIface is None:
		return None
	getCharacterCount = getattr(textIface, "get_character_count", None)
	getText = getattr(textIface, "get_text", None)
	if not callable(getCharacterCount) or not callable(getText):
		return None
	try:
		characterCount = int(getCharacterCount() or 0)
	except Exception:
		characterCount = 0
	if characterCount <= 0:
		return None
	try:
		return _sanitizeUtterance(getText(0, characterCount) or "") or None
	except Exception:
		try:
			return _sanitizeUtterance(getText(0, -1) or "") or None
		except Exception:
			return None


def _getAccessibleRoleEnum(accessible):
	if accessible is None:
		return None
	try:
		return accessible.get_role()
	except Exception:
		return None


def _getAccessibleChild(accessible, index: int):
	if accessible is None:
		return None
	try:
		return accessible.get_child_at_index(index)
	except Exception:
		return None


def _getAccessibleChildCount(accessible) -> int:
	if accessible is None:
		return 0
	try:
		return int(accessible.get_child_count() or 0)
	except Exception:
		return 0


def _iterAccessibleDescendants(accessible, *, maxNodes: int = 256):
	if accessible is None or maxNodes <= 0:
		return
	pending = [_getAccessibleChild(accessible, index) for index in range(_getAccessibleChildCount(accessible))]
	visited = 0
	while pending and visited < maxNodes:
		node = pending.pop(0)
		if node is None:
			continue
		visited += 1
		yield node
		for index in range(_getAccessibleChildCount(node)):
			child = _getAccessibleChild(node, index)
			if child is not None:
				pending.append(child)


def _normalizeComparisonText(text: str | None) -> str:
	if not text:
		return ""
	return " ".join(text.casefold().split())


def _stringsAreRedundant(first: str | None, second: str | None) -> bool:
	if not first or not second:
		return False
	firstKey = _normalizeComparisonText(first)
	secondKey = _normalizeComparisonText(second)
	if not firstKey or not secondKey:
		return False
	return firstKey == secondKey


def _appendUtterancePart(parts: list[str], part: str | None) -> None:
	part = _sanitizeUtterance(part or "")
	if not part:
		return
	if any(_stringsAreRedundant(existingPart, part) for existingPart in parts):
		return
	parts.append(part)


def _extendUtteranceParts(parts: list[str], candidates: tuple[str, ...] | list[str]) -> None:
	for candidate in candidates:
		_appendUtterancePart(parts, candidate)


def _getAccessibleAttributes(accessible) -> tuple[tuple[str, str], ...]:
	if accessible is None:
		return ()
	getAttributesAsArray = getattr(accessible, "get_attributes_as_array", None)
	if callable(getAttributesAsArray):
		try:
			rawAttributes = getAttributesAsArray()
		except Exception:
			rawAttributes = None
		else:
			parsed: list[tuple[str, str]] = []
			for rawAttribute in rawAttributes or ():
				rawAttribute = str(rawAttribute)
				if ":" in rawAttribute:
					key, value = rawAttribute.split(":", 1)
				elif "=" in rawAttribute:
					key, value = rawAttribute.split("=", 1)
				else:
					continue
				key = key.strip()
				value = _sanitizeUtterance(value) or ""
				if key and value:
					parsed.append((key, value))
			if parsed:
				return tuple(parsed)
	getAttributes = getattr(accessible, "get_attributes", None)
	if not callable(getAttributes):
		return ()
	try:
		attributes = getAttributes()
	except Exception:
		return ()
	if not attributes:
		return ()
	if hasattr(attributes, "items"):
		items = attributes.items()
	else:
		try:
			items = list(attributes)
		except Exception:
			return ()
	parsed = []
	for item in items:
		if not isinstance(item, tuple) or len(item) != 2:
			continue
		key, value = item
		key = str(key).strip()
		value = _sanitizeUtterance(str(value))
		if key and value:
			parsed.append((key, value))
	return tuple(parsed)


def _getAccessibleAttributeValue(accessible, attributeName: str) -> str | None:
	attributeKey = attributeName.casefold()
	for key, value in _getAccessibleAttributes(accessible):
		if key.casefold() == attributeKey:
			return value
	return None


def _iterAccessibleAttributeCandidates(accessible) -> tuple[str, ...]:
	preferredKeys = (
		"accessible-name",
		"label",
		"displayed-label",
		"displayed_text",
		"displayed-text",
		"title",
		"tooltip-text",
		"placeholder-text",
	)
	attributeMap = dict(_getAccessibleAttributes(accessible))
	candidates: list[str] = []
	for key in preferredKeys:
		value = attributeMap.get(key)
		if value and value not in candidates:
			candidates.append(value)
	for key, value in attributeMap.items():
		keyLower = key.casefold()
		if ("label" in keyLower or "name" in keyLower or "title" in keyLower) and value not in candidates:
			candidates.append(value)
	return tuple(candidates)


def _iterRelationTargets(accessible, relationTypes: set[object], *, maxTargets: int = 8):
	if accessible is None:
		return
	getRelationSet = getattr(accessible, "get_relation_set", None)
	if not callable(getRelationSet):
		return
	try:
		relationSet = getRelationSet()
	except Exception:
		return
	if relationSet is None:
		return
	try:
		relations = list(relationSet)
	except TypeError:
		relations = []
	targetCount = 0
	for relation in relations:
		getRelationType = getattr(relation, "get_relation_type", None)
		if not callable(getRelationType):
			continue
		try:
			relationType = getRelationType()
		except Exception:
			continue
		if relationType not in relationTypes:
			continue
		getTarget = getattr(relation, "get_target", None)
		getTargetCount = getattr(relation, "get_n_targets", None)
		if not callable(getTarget) or not callable(getTargetCount):
			continue
		try:
			relationTargetCount = int(getTargetCount() or 0)
		except Exception:
			relationTargetCount = 0
		for targetIndex in range(max(0, relationTargetCount)):
			try:
				target = getTarget(targetIndex)
			except Exception:
				continue
			if target is None:
				continue
			yield target
			targetCount += 1
			if targetCount >= maxTargets:
				return


def _getDisplayedLabel(accessible) -> str | None:
	Atspi = importAtspi()
	relationType = getattr(Atspi.RelationType, "LABELLED_BY", None)
	if relationType is None:
		return None
	labelParts: list[str] = []
	for label in _iterRelationTargets(accessible, {relationType}):
		text = _getAccessibleSelfName(label) or _getAccessibleTextContent(label)
		if text and text not in labelParts:
			labelParts.append(text)
	if not labelParts:
		return None
	return " ".join(labelParts)


def _isLikelyContainerDescription(text: str | None) -> bool:
	if not text:
		return False
	text = _normalizeComparisonText(text)
	return bool(
		re.search(r"\b(containing|contains)\s+\d+\s+items?\b", text)
		or re.search(r"\b\d+\s+items?\b", text)
	)


def _isShortcutLike(text: str | None) -> bool:
	if not text:
		return False
	textLower = text.casefold()
	return any(
		token in textLower
		for token in (
			"ctrl",
			"control",
			"alt",
			"shift",
			"super",
			"meta",
		)
	)


def _getSnapshotName(snapshot) -> str | None:
	if snapshot is None:
		return None
	name = _sanitizeUtterance(getattr(snapshot, "name", None) or "") or None
	if not name or _isLikelyContainerDescription(name):
		return None
	return name


def _getPresentableDescendantNames(accessible, *, maxParts: int = 3) -> tuple[str, ...]:
	Atspi = importAtspi()
	skipRoles = {
		Atspi.Role.SECTION,
		Atspi.Role.PARAGRAPH,
		Atspi.Role.TABLE,
		Atspi.Role.TABLE_CELL,
		Atspi.Role.TABLE_ROW,
		Atspi.Role.TABLE_COLUMN_HEADER,
		Atspi.Role.TABLE_ROW_HEADER,
		Atspi.Role.LINK,
		Atspi.Role.IMAGE,
		Atspi.Role.SEPARATOR,
	}
	primaryRoles = {
		Atspi.Role.LABEL,
		Atspi.Role.STATIC,
		Atspi.Role.TEXT,
	}
	primaryCandidates: list[str] = []
	fallbackCandidates: list[str] = []
	for descendant in _iterAccessibleDescendants(accessible):
		descendantRole = _getAccessibleRoleEnum(descendant)
		if descendantRole in skipRoles:
			continue
		candidate = (
			_getAccessibleTextContent(descendant)
			or _getAccessibleSelfName(descendant)
			or next(iter(_iterAccessibleAttributeCandidates(descendant)), None)
		)
		if not candidate or _isShortcutLike(candidate):
			continue
		targetCandidates = primaryCandidates if descendantRole in primaryRoles else fallbackCandidates
		allCandidates = (*primaryCandidates, *fallbackCandidates)
		if any(_stringsAreRedundant(existingCandidate, candidate) for existingCandidate in allCandidates):
			continue
		targetCandidates.append(candidate)
		if len(primaryCandidates) + len(fallbackCandidates) >= maxParts:
			break
	return tuple((*primaryCandidates, *fallbackCandidates)[:maxParts])


def _shouldUseDescendantNameTraversal(roleEnum, childCount: int) -> bool:
	if roleEnum is None or childCount <= 0:
		return False
	Atspi = importAtspi()
	return roleEnum in {
		Atspi.Role.CHECK_MENU_ITEM,
		Atspi.Role.LABEL,
		Atspi.Role.MENU,
		Atspi.Role.MENU_ITEM,
		Atspi.Role.PANEL,
		Atspi.Role.POPUP_MENU,
		Atspi.Role.PUSH_BUTTON,
		Atspi.Role.PUSH_BUTTON_MENU,
		Atspi.Role.RADIO_MENU_ITEM,
		Atspi.Role.STATIC,
		Atspi.Role.TEXT,
		Atspi.Role.TOGGLE_BUTTON,
	}


def _getAccessibleLabelAndName(
	accessible,
	*,
	snapshot=None,
	nameOverride: str | None = None,
	allowDescendantTraversal: bool = False,
) -> tuple[str, ...]:
	roleEnum = _getAccessibleRoleEnum(accessible)
	childCount = _getAccessibleChildCount(accessible)
	label = _getDisplayedLabel(accessible)
	name = _getAccessibleSelfName(accessible, nameOverride=nameOverride)
	if not name:
		name = _getAccessibleTextContent(accessible)
	if not name:
		name = next(iter(_iterAccessibleAttributeCandidates(accessible)), None)
	if not name:
		description = _getAccessibleDescription(accessible)
		if description and not _isLikelyContainerDescription(description):
			name = description
	if not name:
		name = _getSnapshotName(snapshot)
	if label and name and _stringsAreRedundant(label, name):
		return (label,)
	if label and name:
		return (label, name)
	if label:
		return (label,)
	if name:
		return (name,)
	if allowDescendantTraversal and _shouldUseDescendantNameTraversal(roleEnum, childCount):
		descendantNames = _getPresentableDescendantNames(accessible)
		if descendantNames:
			return descendantNames
	menuRoles = {
		importAtspi().Role.CHECK_MENU_ITEM,
		importAtspi().Role.MENU,
		importAtspi().Role.MENU_ITEM,
		importAtspi().Role.POPUP_MENU,
		importAtspi().Role.RADIO_MENU_ITEM,
	}
	if (
		name
		and not _isLikelyContainerDescription(name)
		and not (childCount > 0 and roleEnum in menuRoles)
	):
		return (name,)
	return ()


def _getAccessibleStaticText(
	accessible,
	*,
	snapshot=None,
	exclude: tuple[str, ...] = (),
	maxParts: int = 2,
) -> tuple[str, ...]:
	if accessible is None or maxParts <= 0:
		return ()
	parts: list[str] = []
	description = _getAccessibleDescription(accessible)
	if description and not _isLikelyContainerDescription(description):
		if not any(_stringsAreRedundant(description, existingPart) for existingPart in (*exclude, *parts)):
			parts.append(description)
	if len(parts) >= maxParts:
		return tuple(parts[:maxParts])
	for candidate in _getPresentableDescendantNames(accessible, maxParts=maxParts + len(exclude)):
		if any(_stringsAreRedundant(candidate, existingPart) for existingPart in (*exclude, *parts)):
			continue
		parts.append(candidate)
		if len(parts) >= maxParts:
			break
	if not parts:
		snapshotName = _getSnapshotName(snapshot)
		if snapshotName and not any(
			_stringsAreRedundant(snapshotName, existingPart) for existingPart in exclude
		):
			parts.append(snapshotName)
	return tuple(parts[:maxParts])


def _getAcceleratorLabelForSequence(sequence: str) -> str:
	sequence = _sanitizeUtterance(sequence)
	if not sequence:
		return ""
	try:
		import gi

		gi.require_version("Gtk", "3.0")
		from gi.repository import Gtk

		if "+" in sequence and "<" not in sequence:
			tokens = sequence.split("+")
			sequence = "".join(f"<{part}>" for part in tokens[:-1]) + tokens[-1]
		key, modifiers = Gtk.accelerator_parse(sequence)
		result = Gtk.accelerator_get_label(key, modifiers)
		if result and not result.endswith("+"):
			return _sanitizeUtterance(result)
	except Exception:
		pass
	return (
		sequence.replace("<Primary>", "Control+")
		.replace("<Ctrl>", "Control+")
		.replace("<control>", "Control+")
		.replace("<Shift>", "Shift+")
		.replace("<shift>", "Shift+")
		.replace("<Alt>", "Alt+")
		.replace("<alt>", "Alt+")
		.replace("<Super>", "Super+")
		.replace("<super>", "Super+")
		.replace("<Meta>", "Meta+")
		.replace("<meta>", "Meta+")
		.replace("<", "")
		.replace(">", "")
	)


def _getAccessibleActionKeyBinding(accessible) -> str:
	getActionCount = getattr(accessible, "get_n_actions", None)
	getKeyBinding = getattr(accessible, "get_key_binding", None)
	if not callable(getActionCount) or not callable(getKeyBinding):
		return ""
	try:
		actionCount = int(getActionCount() or 0)
	except Exception:
		return ""
	for actionIndex in range(max(0, actionCount)):
		try:
			keyBinding = _sanitizeUtterance(getKeyBinding(actionIndex) or "")
		except Exception:
			continue
		if keyBinding and keyBinding != "<VoidSymbol>":
			return keyBinding
	return ""


def _getAccessibleKeyboardInfo(accessible) -> tuple[str | None, str | None]:
	keyshortcuts = _getAccessibleAttributeValue(accessible, "keyshortcuts")
	if keyshortcuts:
		sequences = [
			_getAcceleratorLabelForSequence(token)
			for token in keyshortcuts.split(" ")
			if token
		]
		sequences = [sequence for sequence in sequences if sequence]
		if sequences:
			mnemonic = sequences[0] if len(sequences[0]) == 1 else None
			accelerator = " ".join(sequences) if any(len(sequence) > 1 for sequence in sequences) else None
			return mnemonic, accelerator
	keyBinding = _getAccessibleActionKeyBinding(accessible)
	if not keyBinding:
		return None, None
	parts = [_getAcceleratorLabelForSequence(part) for part in keyBinding.split(";") if part]
	parts = [part for part in parts if part]
	if not parts:
		return None, None
	mnemonic = parts[0] if len(parts[0]) == 1 else None
	accelerator = parts[-1] if any(len(part) > 1 for part in parts) else None
	return mnemonic, accelerator


def _shouldAlwaysSpeakRole(snapshot) -> bool:
	import controlTypes

	return snapshot.role in {
		controlTypes.Role.CHECKMENUITEM,
		controlTypes.Role.MENU,
		controlTypes.Role.MENUITEM,
		controlTypes.Role.POPUPMENU,
		controlTypes.Role.RADIOMENUITEM,
	}


def _shouldSpeakRole(accessible, snapshot) -> bool:
	import controlTypes

	roleEnum = _getAccessibleRoleEnum(accessible)
	if roleEnum is not None:
		Atspi = importAtspi()
		if roleEnum in {
			Atspi.Role.FILLER,
			Atspi.Role.LABEL,
			Atspi.Role.MENU_ITEM,
			Atspi.Role.PARAGRAPH,
			Atspi.Role.REDUNDANT_OBJECT,
			Atspi.Role.SECTION,
			Atspi.Role.STATIC,
			Atspi.Role.TABLE_CELL,
			Atspi.Role.UNKNOWN,
		}:
			return False
	return snapshot.role not in controlTypes.silentRolesOnFocus


def _getStateLabels(snapshot) -> list[str]:
	import controlTypes

	try:
		return list(
			controlTypes.processAndLabelStates(
			snapshot.role,
			set(snapshot.states),
			controlTypes.OutputReason.FOCUS,
		)
		)
	except Exception:
		return [
			state.displayString
			for state in sorted(snapshot.states, key=lambda state: state.value)
			if state.name not in {"FOCUSED", "FOCUSABLE"}
		]


def _getFilteredStateLabels(
	snapshot,
	*,
	allowedStateNames: set[str] | None = None,
	excludedStateNames: set[str] | None = None,
) -> list[str]:
	import controlTypes

	filteredStates = set(snapshot.states)
	if allowedStateNames is not None:
		filteredStates = {
			state
			for state in filteredStates
			if state.name in allowedStateNames
		}
	if excludedStateNames:
		filteredStates = {
			state
			for state in filteredStates
			if state.name not in excludedStateNames
		}
	try:
		return list(
			controlTypes.processAndLabelStates(
				snapshot.role,
				filteredStates,
				controlTypes.OutputReason.FOCUS,
			)
		)
	except Exception:
		return [
			state.displayString
			for state in sorted(filteredStates, key=lambda state: state.value)
			if state.name not in {"FOCUSED", "FOCUSABLE"}
		]


def _buildDefaultAnnouncementParts(
	accessible,
	*,
	snapshot,
	nameOverride: str | None = None,
) -> list[str]:
	import controlTypes

	labelAndName = _getAccessibleLabelAndName(
		accessible,
		snapshot=snapshot,
		nameOverride=nameOverride,
	)
	mnemonic, accelerator = _getAccessibleKeyboardInfo(accessible)
	if (
		not labelAndName
		and snapshot.role in {
			controlTypes.Role.FILLER,
			controlTypes.Role.LABEL,
			controlTypes.Role.PANEL,
			controlTypes.Role.STATICTEXT,
		}
		and not mnemonic
		and not accelerator
	):
		return []
	parts: list[str] = []
	_extendUtteranceParts(parts, list(labelAndName))
	if _shouldAlwaysSpeakRole(snapshot) or _shouldSpeakRole(accessible, snapshot) or not labelAndName:
		_appendUtterancePart(parts, snapshot.role.displayString)
	_extendUtteranceParts(parts, _getStateLabels(snapshot))
	_appendUtterancePart(parts, mnemonic)
	_appendUtterancePart(parts, accelerator)
	if not parts:
		_appendUtterancePart(parts, snapshot.applicationName)
	elif not labelAndName:
		_appendUtterancePart(parts, snapshot.applicationName)
	return parts


def _buildMenuItemAnnouncementParts(
	accessible,
	*,
	snapshot,
	nameOverride: str | None = None,
) -> list[str]:
	labelAndName = _getAccessibleLabelAndName(
		accessible,
		snapshot=snapshot,
		nameOverride=nameOverride,
		allowDescendantTraversal=True,
	)
	parts: list[str] = []
	_extendUtteranceParts(parts, list(labelAndName))
	if not parts:
		_extendUtteranceParts(
			parts,
			list(_getAccessibleStaticText(accessible, snapshot=snapshot, maxParts=1)),
		)
	_extendUtteranceParts(
		parts,
		_getFilteredStateLabels(
			snapshot,
			allowedStateNames={
				"CHECKED",
				"HALFCHECKED",
				"PRESSED",
				"EXPANDED",
				"COLLAPSED",
				"UNAVAILABLE",
			},
		),
	)
	mnemonic, accelerator = _getAccessibleKeyboardInfo(accessible)
	_appendUtterancePart(parts, mnemonic)
	_appendUtterancePart(parts, accelerator)
	if not parts:
		_appendUtterancePart(parts, snapshot.role.displayString)
	return parts


def _buildLabelAnnouncementParts(
	accessible,
	*,
	snapshot,
	nameOverride: str | None = None,
) -> list[str]:
	labelAndName = _getAccessibleLabelAndName(
		accessible,
		snapshot=snapshot,
		nameOverride=nameOverride,
	)
	parts: list[str] = []
	_extendUtteranceParts(parts, list(labelAndName))
	if not parts:
		_extendUtteranceParts(
			parts,
			list(_getAccessibleStaticText(accessible, snapshot=snapshot, maxParts=1)),
		)
	return parts


def _buildPanelAnnouncementParts(
	accessible,
	*,
	snapshot,
	nameOverride: str | None = None,
) -> list[str]:
	textContent = _getAccessibleTextContent(accessible)
	parts: list[str] = []
	_appendUtterancePart(parts, textContent)
	if not parts:
		_extendUtteranceParts(
			parts,
			list(
				_getAccessibleLabelAndName(
					accessible,
					snapshot=snapshot,
					nameOverride=nameOverride,
				),
			),
		)
	_extendUtteranceParts(
		parts,
		list(
			_getAccessibleStaticText(
				accessible,
				snapshot=snapshot,
				exclude=tuple(parts),
			),
		),
	)
	if parts and _shouldSpeakRole(accessible, snapshot):
		_appendUtterancePart(parts, snapshot.role.displayString)
	return parts


def _buildRoleSpecificAnnouncementParts(
	accessible,
	*,
	snapshot,
	nameOverride: str | None = None,
) -> list[str]:
	roleEnum = _getAccessibleRoleEnum(accessible)
	if roleEnum is None:
		return _buildDefaultAnnouncementParts(
			accessible,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
	Atspi = importAtspi()
	if roleEnum in {
		Atspi.Role.CHECK_MENU_ITEM,
		Atspi.Role.MENU_ITEM,
		Atspi.Role.RADIO_MENU_ITEM,
		Atspi.Role.TEAROFF_MENU_ITEM,
	}:
		return _buildMenuItemAnnouncementParts(
			accessible,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
	if roleEnum == Atspi.Role.LABEL:
		return _buildLabelAnnouncementParts(
			accessible,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
	if roleEnum in {
		Atspi.Role.FILLER,
		Atspi.Role.PANEL,
		Atspi.Role.STATIC,
		Atspi.Role.TEXT,
	}:
		return _buildPanelAnnouncementParts(
			accessible,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
	return _buildDefaultAnnouncementParts(
		accessible,
		snapshot=snapshot,
		nameOverride=nameOverride,
	)


def buildAccessibleAnnouncement(
	accessible,
	*,
	snapshot=None,
	nameOverride: str | None = None,
) -> str:
	if accessible is None and snapshot is None:
		return ""
	if snapshot is None and accessible is not None:
		try:
			snapshot = snapshotAccessibleObject(accessible)
		except Exception:
			snapshot = None
	if snapshot is None:
		return ""
	parts = _buildRoleSpecificAnnouncementParts(
		accessible,
		snapshot=snapshot,
		nameOverride=nameOverride,
	)
	if not parts and snapshot.applicationName:
		parts = [snapshot.applicationName]
	return _sanitizeUtterance(" ".join(part for part in parts if part))


def buildFocusAnnouncement(snapshot) -> str:
	return buildAccessibleAnnouncement(None, snapshot=snapshot)


@dataclass(frozen=True)
class EspeakRequest:
	text: str
	interrupt: bool = True


class EspeakSpeaker:
	def __init__(
		self,
		*,
		log: Any,
		rate: int = 220,
		pitch: int = 50,
		amplitude: int = 100,
	) -> None:
		self._log = log
		self._rate = rate
		self._pitch = pitch
		self._amplitude = amplitude
		self._binary = shutil.which("espeak-ng")
		self._voiceCandidates = _candidateVoiceNames()
		self._requests: Queue[EspeakRequest] = Queue()
		self._stopEvent = threading.Event()
		self._worker = threading.Thread(
			target=self._run,
			name="linuxEspeakSpeaker",
			daemon=True,
		)
		self._processLock = threading.Lock()
		self._currentProcess: subprocess.Popen[str] | None = None
		self._lastText = ""
		self._lastSpokenAt = 0.0

	@property
	def isAvailable(self) -> bool:
		return self._binary is not None

	def start(self) -> None:
		if not self.isAvailable:
			raise RuntimeError("espeak-ng is not available")
		self._worker.start()

	def terminate(self) -> None:
		self._stopEvent.set()
		self.cancel()
		self._requests.put_nowait(EspeakRequest(text="", interrupt=False))
		if self._worker.is_alive():
			self._worker.join(timeout=2.0)

	def speak(self, text: str, *, interrupt: bool = True) -> bool:
		text = _sanitizeUtterance(text)
		if not self.isAvailable or not text:
			return False
		now = time.monotonic()
		if text == self._lastText and now - self._lastSpokenAt < 0.75:
			return False
		if interrupt:
			self.cancel()
		self._lastText = text
		self._lastSpokenAt = now
		self._requests.put_nowait(EspeakRequest(text=text, interrupt=interrupt))
		return True

	def cancel(self) -> None:
		while True:
			try:
				self._requests.get_nowait()
			except Empty:
				break
		with self._processLock:
			process = self._currentProcess
		if process is None:
			return
		try:
			process.terminate()
		except ProcessLookupError:
			return
		except Exception:
			self._log.debug("Failed to terminate current espeak-ng process", exc_info=True)

	def _run(self) -> None:
		while not self._stopEvent.is_set():
			try:
				request = self._requests.get(timeout=0.1)
			except Empty:
				continue
			if not request.text:
				continue
			try:
				self._speakRequest(request)
			except Exception:
				self._log.debug("Linux espeak-ng request failed", exc_info=True)

	def _speakRequest(self, request: EspeakRequest) -> None:
		voiceCandidates = list(self._voiceCandidates) + [None]
		lastReturnCode = 0
		for voice in voiceCandidates:
			command = [
				self._binary,
				"-s",
				str(self._rate),
				"-p",
				str(self._pitch),
				"-a",
				str(self._amplitude),
				"-z",
			]
			if voice:
				command.extend(("-v", voice))
			command.append(request.text)
			process = subprocess.Popen(
				command,
				stdin=subprocess.DEVNULL,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
				text=True,
			)
			with self._processLock:
				self._currentProcess = process
			try:
				returnCode = process.wait()
			finally:
				with self._processLock:
					if self._currentProcess is process:
						self._currentProcess = None
			lastReturnCode = returnCode
			if returnCode == 0:
				return
			if returnCode == -15:
				return
		self._log.debug("espeak-ng exited with code %s for utterance %r", lastReturnCode, request.text)
