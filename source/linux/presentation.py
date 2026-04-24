# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from linux import speech as speechHelpers
from linux.accessibility import (
	_getAccessibleChildCount,
	_getAccessibleParent,
	_getAccessibleRoleEnum,
	_getFocusedState,
	_getSelectedAccessibleChild,
	clearAccessibleCache,
	snapshotAccessibleObject,
)


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
		self._notifyCallback: Callable[
			[Any, object | None, object | None],
			"LinuxPresentationResult | None",
		] | None = None

	def set_notify_callback(
		self,
		callback: Callable[[Any, object | None, object | None], "LinuxPresentationResult | None"],
	) -> None:
		self._notifyCallback = callback

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
		notify_script: bool = True,
		force: bool = False,
		snapshot: object | None = None,
	) -> "LinuxPresentationResult | None":
		clearAccessibleCache(obj)
		if not force and obj is self._locusOfFocus:
			if snapshot is not None:
				self._focusSnapshot = snapshot
			return None
		oldFocus = self._locusOfFocus
		self._priorFocus = oldFocus
		self._priorFocusSnapshot = self._focusSnapshot
		self._locusOfFocus = obj
		self._focusSnapshot = snapshot
		if notify_script and self._notifyCallback is not None:
			return self._notifyCallback(event, oldFocus, self._locusOfFocus)
		return None


class LinuxAXUtilities:
	@staticmethod
	def is_focused(obj: object | None) -> bool:
		return _getFocusedState(obj)

	@staticmethod
	def is_ancestor(ancestor: object | None, obj: object | None) -> bool:
		current = obj
		while current is not None:
			if current is ancestor:
				return True
			current = _getAccessibleParent(current)
		return False

	@staticmethod
	def selected_children(obj: object | None) -> list[object]:
		child = _getSelectedAccessibleChild(obj)
		return [child] if child is not None else []

	@staticmethod
	def selected_child_count(obj: object | None) -> int:
		return len(LinuxAXUtilities.selected_children(obj))

	@staticmethod
	def get_selected_child_for_focus(
		obj: object | None,
		focus: object | None,
		should_skip: Callable[[object], bool] | None = None,
	) -> object | None:
		selected = LinuxAXUtilities.selected_children(obj)
		if focus in selected:
			return None
		for child in selected:
			if should_skip is not None and should_skip(child):
				continue
			if LinuxAXUtilities.is_ancestor(focus, child):
				return None
			return child
		return None

	@staticmethod
	def is_table_cell(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.TABLE_CELL

	@staticmethod
	def is_table_related(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) in {
			Atspi.Role.TABLE,
			Atspi.Role.TABLE_CELL,
			Atspi.Role.TABLE_ROW,
			Atspi.Role.TABLE_COLUMN_HEADER,
			Atspi.Role.TABLE_ROW_HEADER,
			Atspi.Role.TREE_TABLE,
		}

	@staticmethod
	def is_tree_or_tree_table(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) in {Atspi.Role.TREE, Atspi.Role.TREE_TABLE}

	@staticmethod
	def find_ancestor(
		obj: object | None,
		predicate: Callable[[object | None], bool],
	) -> object | None:
		current = _getAccessibleParent(obj)
		while current is not None:
			if predicate(current):
				return current
			current = _getAccessibleParent(current)
		return None

	@staticmethod
	def is_toggle_button(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.TOGGLE_BUTTON

	@staticmethod
	def is_combo_box(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.COMBO_BOX

	@staticmethod
	def is_layered_pane(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.LAYERED_PANE

	@staticmethod
	def is_window(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.WINDOW

	@staticmethod
	def is_icon_or_canvas(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) in {Atspi.Role.ICON, Atspi.Role.CANVAS}

	@staticmethod
	def is_menu_bar(obj: object | None) -> bool:
		Atspi = speechHelpers.importAtspi()
		return _getAccessibleRoleEnum(obj) == Atspi.Role.MENU_BAR

	@staticmethod
	def get_active_descendant_checked(
		container: object | None,
		reportedChild: object | None,
	) -> object | None:
		if reportedChild is None:
			return None
		if _getAccessibleParent(reportedChild) is container:
			return reportedChild
		return reportedChild


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
		script,
		obj: object | None,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
		interrupt: bool = True,
		alreadyFocused: bool = False,
		priorObj: object | None = None,
	) -> LinuxPresentationResult | None:
		if obj is None:
			return None
		context = LinuxGeneratorContext(
			focus=self._focusManager.get_locus_of_focus(),
			priorFocus=priorObj if priorObj is not None else self._focusManager.get_prior_focus(),
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
		self._focusManager.set_notify_callback(self.locus_of_focus_changed)

	def locus_of_focus_changed(
		self,
		event: Any,
		old_focus: object | None,
		new_focus: object | None,
	) -> LinuxPresentationResult | None:
		if new_focus is None:
			return None
		if old_focus is new_focus and not (
			event is not None
			and getattr(event, "eventType", "").startswith("object:property-change:accessible-name")
		):
			return None
		return self.present_object(
			new_focus,
			priorObj=old_focus,
			interrupt=True,
		)

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
		priorObj: object | None = None,
	) -> LinuxPresentationResult | None:
		return self._presentationManager.present_object(
			self,
			obj,
			snapshot=snapshot,
			nameOverride=nameOverride,
			interrupt=interrupt,
			alreadyFocused=alreadyFocused,
			priorObj=priorObj,
		)

	def _on_focused_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		if not bool(getattr(event, "detail1", 0)):
			return None
		if not LinuxAXUtilities.is_focused(event.eventSourceAccessible):
			clearAccessibleCache(event.eventSourceAccessible)
			if not LinuxAXUtilities.is_focused(event.eventSourceAccessible):
				return None
		snapshot = resolveSnapshot(event)
		obj = event.sourceAccessible
		if obj is None:
			return None
		if _getAccessibleChildCount(obj) and not LinuxAXUtilities.is_combo_box(obj):
			selectedChildren = LinuxAXUtilities.selected_children(obj)
			if selectedChildren:
				obj = selectedChildren[0]
				snapshot = snapshotAccessibleObject(obj)
		return self._focusManager.set_locus_of_focus(event, obj, snapshot=snapshot)

	def _on_active_descendant_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		if not event.shouldAnnounce:
			return None
		snapshot = resolveSnapshot(event)
		return self._focusManager.set_locus_of_focus(event, event.sourceAccessible, snapshot=snapshot)

	def _on_selection_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		del resolveSnapshot
		focus = self._focusManager.get_locus_of_focus()
		child = LinuxAXUtilities.get_selected_child_for_focus(
			event.eventSourceAccessible,
			focus,
		)
		if child is None:
			return None
		return self._focusManager.set_locus_of_focus(
			event,
			child,
			snapshot=snapshotAccessibleObject(child),
		)

	def _on_selected_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		del resolveSnapshot
		return None

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
		return self._focusManager.set_locus_of_focus(
			event,
			event.sourceAccessible,
			force=True,
			snapshot=snapshot,
		)


class LinuxGtkScript(LinuxDefaultScript):
	def locus_of_focus_changed(
		self,
		event: Any,
		old_focus: object | None,
		new_focus: object | None,
	) -> LinuxPresentationResult | None:
		if LinuxAXUtilities.is_toggle_button(new_focus):
			new_focus = (
				LinuxAXUtilities.find_ancestor(new_focus, LinuxAXUtilities.is_combo_box)
				or new_focus
			)
			self._focusManager.set_locus_of_focus(
				event,
				new_focus,
				notify_script=False,
				force=True,
				snapshot=snapshotAccessibleObject(new_focus),
			)
		return super().locus_of_focus_changed(event, old_focus, new_focus)

	def _on_active_descendant_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		if LinuxAXUtilities.is_table_related(event.eventSourceAccessible):
			clearAccessibleCache(event.sourceAccessible)
			clearAccessibleCache(event.eventSourceAccessible)
		focus = self._focusManager.get_locus_of_focus()
		if LinuxAXUtilities.is_table_cell(focus):
			table = LinuxAXUtilities.find_ancestor(focus, LinuxAXUtilities.is_tree_or_tree_table)
			if table is not None and table is not event.eventSourceAccessible:
				return None
		child = LinuxAXUtilities.get_active_descendant_checked(
			event.eventSourceAccessible,
			event.sourceAccessible,
		)
		if child is not None and child is not event.sourceAccessible:
			return self._focusManager.set_locus_of_focus(
				event,
				child,
				snapshot=snapshotAccessibleObject(child),
			)
		return super()._on_active_descendant_changed(event, resolveSnapshot=resolveSnapshot)

	def _on_focused_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		focus = self._focusManager.get_locus_of_focus()
		if LinuxAXUtilities.is_ancestor(focus, event.eventSourceAccessible) and LinuxAXUtilities.is_focused(focus):
			return None
		return super()._on_focused_changed(event, resolveSnapshot=resolveSnapshot)

	def _on_selection_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		focus = self._focusManager.get_locus_of_focus()
		if (
			LinuxAXUtilities.is_toggle_button(focus)
			and LinuxAXUtilities.is_combo_box(event.eventSourceAccessible)
			and LinuxAXUtilities.is_ancestor(focus, event.eventSourceAccessible)
		):
			return super()._on_selection_changed(event, resolveSnapshot=resolveSnapshot)
		if LinuxAXUtilities.is_combo_box(event.eventSourceAccessible) and not LinuxAXUtilities.is_focused(
			event.eventSourceAccessible,
		):
			return None
		if (
			LinuxAXUtilities.is_layered_pane(event.eventSourceAccessible)
			and LinuxAXUtilities.selected_child_count(event.eventSourceAccessible) > 1
		):
			return None
		return super()._on_selection_changed(event, resolveSnapshot=resolveSnapshot)

	def _on_selected_changed(
		self,
		event,
		*,
		resolveSnapshot: Callable[[Any], object | None],
	) -> LinuxPresentationResult | None:
		if (
			LinuxAXUtilities.is_table_cell(event.eventSourceAccessible)
			and LinuxAXUtilities.find_ancestor(event.eventSourceAccessible, LinuxAXUtilities.is_window)
			is not None
		):
			if bool(getattr(event, "detail1", 0)):
					return self._focusManager.set_locus_of_focus(
						event,
						event.eventSourceAccessible,
						snapshot=snapshotAccessibleObject(event.eventSourceAccessible),
					)
			if self._focusManager.get_locus_of_focus() is event.eventSourceAccessible:
				self._focusManager.set_locus_of_focus(
					event,
					None,
					notify_script=False,
					force=True,
				)
				return None
		return super()._on_selected_changed(event, resolveSnapshot=resolveSnapshot)
