# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from linux import speech as speechHelpers
from linux.accessibility import snapshotAccessibleObject


@dataclass(frozen=True)
class LinuxGeneratorContext:
	focus: object | None
	priorFocus: object | None
	alreadyFocused: bool = False
	interrupt: bool = True


@dataclass(frozen=True)
class LinuxPresentationResult:
	accessible: object
	snapshot: object | None
	announcement: str
	interrupt: bool = True


class LinuxFocusManager:
	def __init__(self) -> None:
		self._locusOfFocus: object | None = None
		self._priorFocus: object | None = None
		self._focusSnapshot: object | None = None
		self._priorFocusSnapshot: object | None = None

	def get_locus_of_focus(self) -> object | None:
		return self._locusOfFocus

	def get_prior_focus(self) -> object | None:
		return self._priorFocus

	def get_focus_snapshot(self) -> object | None:
		return self._focusSnapshot

	def get_prior_focus_snapshot(self) -> object | None:
		return self._priorFocusSnapshot

	def set_locus_of_focus(
		self,
		event: Any,
		obj: object | None,
		*,
		snapshot: object | None = None,
	) -> None:
		del event
		if obj is self._locusOfFocus:
			if snapshot is not None:
				self._focusSnapshot = snapshot
			return
		self._priorFocus = self._locusOfFocus
		self._priorFocusSnapshot = self._focusSnapshot
		self._locusOfFocus = obj
		self._focusSnapshot = snapshot


class LinuxSpeechGenerator:
	def _appendParts(self, parts: list[str], newParts: list[str] | tuple[str, ...]) -> None:
		speechHelpers._extendUtteranceParts(parts, list(newParts))

	def _generate_accessible_label(
		self,
		obj: object | None,
	) -> list[str]:
		label = speechHelpers._getDisplayedLabel(obj)
		return [label] if label else []

	def _generate_accessible_name(
		self,
		obj: object | None,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
		allowDescendantTraversal: bool = False,
	) -> list[str]:
		label = speechHelpers._getDisplayedLabel(obj)
		labelAndName = speechHelpers._getAccessibleLabelAndName(
			obj,
			snapshot=snapshot,
			nameOverride=nameOverride,
			allowDescendantTraversal=allowDescendantTraversal,
		)
		if not labelAndName:
			return []
		if not label:
			return list(labelAndName)
		return [
			part
			for part in labelAndName
			if not speechHelpers._stringsAreRedundant(part, label)
		]

	def _generate_accessible_label_and_name(
		self,
		obj: object | None,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
		allowDescendantTraversal: bool = False,
	) -> list[str]:
		return list(
			speechHelpers._getAccessibleLabelAndName(
				obj,
				snapshot=snapshot,
				nameOverride=nameOverride,
				allowDescendantTraversal=allowDescendantTraversal,
			),
		)

	def _generate_accessible_static_text(
		self,
		obj: object | None,
		*,
		snapshot: object | None = None,
		exclude: tuple[str, ...] = (),
	) -> list[str]:
		return list(
			speechHelpers._getAccessibleStaticText(
				obj,
				snapshot=snapshot,
				exclude=exclude,
			),
		)

	def _generate_accessible_role(
		self,
		obj: object | None,
		*,
		snapshot,
	) -> list[str]:
		if not speechHelpers._shouldSpeakRole(obj, snapshot):
			return []
		return [snapshot.role.displayString]

	def _generate_keyboard_mnemonic(self, obj: object | None) -> list[str]:
		mnemonic, _accelerator = speechHelpers._getAccessibleKeyboardInfo(obj)
		return [mnemonic] if mnemonic else []

	def _generate_keyboard_accelerator(self, obj: object | None) -> list[str]:
		_mnemonic, accelerator = speechHelpers._getAccessibleKeyboardInfo(obj)
		return [accelerator] if accelerator else []

	def _generate_state_checked_if_checkable(self, snapshot) -> list[str]:
		return speechHelpers._getFilteredStateLabels(
			snapshot,
			allowedStateNames={"CHECKED", "HALFCHECKED", "PRESSED"},
		)

	def _generate_state_expanded(self, snapshot) -> list[str]:
		return speechHelpers._getFilteredStateLabels(
			snapshot,
			allowedStateNames={"EXPANDED", "COLLAPSED"},
		)

	def _generate_state_sensitive(self, snapshot) -> list[str]:
		return speechHelpers._getFilteredStateLabels(
			snapshot,
			allowedStateNames={"UNAVAILABLE"},
		)

	def _generate_position_in_list(self, obj: object | None) -> list[str]:
		del obj
		return []

	def _generate_default_presentation(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot,
		nameOverride: str | None = None,
	) -> list[str]:
		del context
		parts: list[str] = []
		self._appendParts(
			parts,
			self._generate_accessible_label_and_name(
				obj,
				snapshot=snapshot,
				nameOverride=nameOverride,
			),
		)
		if (
			speechHelpers._shouldAlwaysSpeakRole(snapshot)
			or speechHelpers._shouldSpeakRole(obj, snapshot)
			or not parts
		):
			self._appendParts(
				parts,
				self._generate_accessible_role(obj, snapshot=snapshot),
			)
		self._appendParts(parts, speechHelpers._getStateLabels(snapshot))
		self._appendParts(parts, self._generate_keyboard_mnemonic(obj))
		self._appendParts(parts, self._generate_keyboard_accelerator(obj))
		if not parts and snapshot.applicationName:
			parts.append(snapshot.applicationName)
		return parts

	def _generate_label(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot,
		nameOverride: str | None = None,
	) -> list[str]:
		del context
		parts: list[str] = []
		self._appendParts(parts, self._generate_accessible_label(obj))
		textContent = speechHelpers._getAccessibleTextContent(obj)
		if textContent:
			self._appendParts(parts, [textContent])
		else:
			self._appendParts(
				parts,
				self._generate_accessible_name(
					obj,
					snapshot=snapshot,
					nameOverride=nameOverride,
				),
			)
		self._appendParts(parts, self._generate_accessible_role(obj, snapshot=snapshot))
		return parts

	def _generate_panel(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot,
		nameOverride: str | None = None,
	) -> list[str]:
		del context
		parts: list[str] = []
		textContent = speechHelpers._getAccessibleTextContent(obj)
		if textContent:
			self._appendParts(parts, [textContent])
		if not parts:
			self._appendParts(
				parts,
				self._generate_accessible_label_and_name(
					obj,
					snapshot=snapshot,
					nameOverride=nameOverride,
				),
			)
		self._appendParts(
			parts,
			self._generate_accessible_static_text(
				obj,
				snapshot=snapshot,
				exclude=tuple(parts),
			),
		)
		self._appendParts(parts, self._generate_accessible_role(obj, snapshot=snapshot))
		return parts

	def _generate_menu_item(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot,
		nameOverride: str | None = None,
	) -> list[str]:
		del context
		parts: list[str] = []
		self._appendParts(
			parts,
			self._generate_accessible_label_and_name(
				obj,
				snapshot=snapshot,
				nameOverride=nameOverride,
				allowDescendantTraversal=True,
			),
		)
		if not parts:
			self._appendParts(
				parts,
				self._generate_accessible_static_text(
					obj,
					snapshot=snapshot,
					exclude=tuple(parts),
				),
			)
		self._appendParts(parts, self._generate_accessible_role(obj, snapshot=snapshot))
		self._appendParts(parts, self._generate_state_checked_if_checkable(snapshot))
		self._appendParts(parts, self._generate_state_expanded(snapshot))
		self._appendParts(parts, self._generate_state_sensitive(snapshot))
		self._appendParts(parts, self._generate_keyboard_mnemonic(obj))
		self._appendParts(parts, self._generate_keyboard_accelerator(obj))
		self._appendParts(parts, self._generate_position_in_list(obj))
		return parts

	def _generate_for_role(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot,
		nameOverride: str | None = None,
	) -> list[str]:
		Atspi = speechHelpers.importAtspi()
		roleEnum = speechHelpers._getAccessibleRoleEnum(obj)
		if roleEnum in {
			Atspi.Role.CHECK_MENU_ITEM,
			Atspi.Role.MENU_ITEM,
			Atspi.Role.RADIO_MENU_ITEM,
			Atspi.Role.TEAROFF_MENU_ITEM,
		}:
			return self._generate_menu_item(
				obj,
				context,
				snapshot=snapshot,
				nameOverride=nameOverride,
			)
		if roleEnum == Atspi.Role.LABEL:
			return self._generate_label(
				obj,
				context,
				snapshot=snapshot,
				nameOverride=nameOverride,
			)
		if roleEnum in {
			Atspi.Role.FILLER,
			Atspi.Role.PANEL,
			Atspi.Role.STATIC,
			Atspi.Role.TEXT,
		}:
			return self._generate_panel(
				obj,
				context,
				snapshot=snapshot,
				nameOverride=nameOverride,
			)
		return self._generate_default_presentation(
			obj,
			context,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)

	def generate_speech(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
	) -> str:
		if obj is None and snapshot is None:
			return ""
		if snapshot is None and obj is not None:
			try:
				snapshot = snapshotAccessibleObject(obj)
			except Exception:
				snapshot = None
		if snapshot is None:
			return ""
		parts = self._generate_for_role(
			obj,
			context,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
		if not parts and snapshot.applicationName:
			parts = [snapshot.applicationName]
		return speechHelpers._sanitizeUtterance(" ".join(part for part in parts if part))


class LinuxPresentationManager:
	def __init__(
		self,
		*,
		focusManager: LinuxFocusManager,
		speechGenerator: LinuxSpeechGenerator,
	) -> None:
		self._focusManager = focusManager
		self._speechGenerator = speechGenerator

	def present_object(
		self,
		obj: object | None,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
		interrupt: bool = True,
		alreadyFocused: bool = False,
	) -> LinuxPresentationResult | None:
		if obj is None:
			return None
		context = LinuxGeneratorContext(
			focus=self._focusManager.get_locus_of_focus(),
			priorFocus=self._focusManager.get_prior_focus(),
			alreadyFocused=alreadyFocused,
			interrupt=interrupt,
		)
		announcement = self._speechGenerator.generate_speech(
			obj,
			context,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)
		if not announcement:
			return None
		return LinuxPresentationResult(
			accessible=obj,
			snapshot=snapshot,
			announcement=announcement,
			interrupt=interrupt,
		)


class LinuxDefaultScript:
	def __init__(
		self,
		*,
		focusManager: LinuxFocusManager,
		presentationManager: LinuxPresentationManager,
	) -> None:
		self._focusManager = focusManager
		self._presentationManager = presentationManager

	def handle_event(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		if not event.shouldAnnounce or event.sourceAccessible is None:
			return None
		eventType = event.eventType
		if eventType.startswith("object:state-changed:focused"):
			return self._on_focused_changed(event, resolveSnapshot=resolveSnapshot)
		if eventType.startswith("object:active-descendant-changed"):
			return self._on_active_descendant_changed(event, resolveSnapshot=resolveSnapshot)
		if eventType.startswith("object:selection-changed"):
			return self._on_selection_changed(event, resolveSnapshot=resolveSnapshot)
		if eventType.startswith("object:state-changed:selected"):
			return self._on_selected_changed(event, resolveSnapshot=resolveSnapshot)
		if eventType.startswith("object:property-change:accessible-name"):
			return self._on_name_changed(event, resolveSnapshot=resolveSnapshot)
		return None

	def present_object(
		self,
		obj: object | None,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
		interrupt: bool = True,
		alreadyFocused: bool = False,
	) -> LinuxPresentationResult | None:
		return self._presentationManager.present_object(
			obj,
			snapshot=snapshot,
			nameOverride=nameOverride,
			interrupt=interrupt,
			alreadyFocused=alreadyFocused,
		)

	def _on_focused_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		snapshot = resolveSnapshot(event)
		self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)
		return self.present_object(
			event.sourceAccessible,
			snapshot=snapshot,
			interrupt=True,
		)

	def _on_active_descendant_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		snapshot = resolveSnapshot(event)
		self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)
		return self.present_object(
			event.sourceAccessible,
			snapshot=snapshot,
			interrupt=True,
		)

	def _on_selection_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		snapshot = resolveSnapshot(event)
		self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)
		return self.present_object(
			event.sourceAccessible,
			snapshot=snapshot,
			interrupt=True,
		)

	def _on_selected_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		snapshot = resolveSnapshot(event)
		self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)
		return self.present_object(
			event.sourceAccessible,
			snapshot=snapshot,
			interrupt=True,
			alreadyFocused=True,
		)

	def _on_name_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		focus = self._focusManager.get_locus_of_focus()
		if focus is not event.sourceAccessible and not bool(event.sourceObject and event.sourceObject.focused):
			return None
		snapshot = resolveSnapshot(event)
		self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)
		return self.present_object(
			event.sourceAccessible,
			snapshot=snapshot,
			nameOverride=event.nameOverride,
			interrupt=True,
			alreadyFocused=True,
		)
