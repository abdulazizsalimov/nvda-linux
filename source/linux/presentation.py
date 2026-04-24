# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from linux.speech import buildAccessibleAnnouncement


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
	def generate_speech(
		self,
		obj: object | None,
		context: LinuxGeneratorContext,
		*,
		snapshot: object | None = None,
		nameOverride: str | None = None,
	) -> str:
		del context
		return buildAccessibleAnnouncement(
			obj,
			snapshot=snapshot,
			nameOverride=nameOverride,
		)


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
