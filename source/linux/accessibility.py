# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from .atspi import importAtspi

if TYPE_CHECKING:
	import controlTypes


@dataclass(frozen=True)
class AccessibleSnapshot:
	name: str | None
	role: str | None
	childCount: int
	focused: bool


@dataclass(frozen=True)
class AtspiObjectSnapshot:
	name: str | None
	rawRole: str | None
	role: "controlTypes.Role"
	states: frozenset["controlTypes.State"]
	childCount: int
	focused: bool
	applicationName: str | None

	@property
	def roleName(self) -> str:
		return self.role.name

	@property
	def stateNames(self) -> tuple[str, ...]:
		return tuple(
			state.name
			for state in sorted(self.states, key=lambda state: state.value)
		)


@dataclass(frozen=True)
class FocusEventSnapshot:
	eventType: str
	detail1: int
	detail2: int
	sourceName: str | None
	sourceRole: str | None
	hostApplicationName: str | None
	sourceObject: AtspiObjectSnapshot | None = None


@dataclass(frozen=True)
class DesktopSnapshot:
	desktopCount: int
	desktopName: str | None
	rootChildCount: int
	applications: tuple[AccessibleSnapshot, ...]
	normalizedApplications: tuple[AtspiObjectSnapshot, ...] = ()


class AtspiFocusEventMonitor:
	def __init__(self) -> None:
		Atspi = importAtspi()
		self._Atspi = Atspi
		self._listener = Atspi.EventListener.new(self._handleEvent)
		self._registeredEvents: tuple[str, ...] = ()
		self._pendingEvents: deque[FocusEventSnapshot] = deque(maxlen=32)
		self.latestEvent: FocusEventSnapshot | None = None
		self.latestFocusedObject: AtspiObjectSnapshot | None = None

	@property
	def registeredEvents(self) -> tuple[str, ...]:
		return self._registeredEvents

	@property
	def pendingEventCount(self) -> int:
		return len(self._pendingEvents)

	def register(self, *eventTypes: str) -> tuple[str, ...]:
		if not eventTypes:
			eventTypes = ("object:state-changed:focused",)
		registeredEvents: list[str] = []
		for eventType in eventTypes:
			if self._listener.register(eventType):
				registeredEvents.append(eventType)
		self._registeredEvents = tuple(registeredEvents)
		return self._registeredEvents

	def deregister(self) -> None:
		for eventType in self._registeredEvents:
			try:
				self._listener.deregister(eventType)
			except Exception:
				pass
		self._registeredEvents = ()

	def drainPendingEvents(self) -> tuple[FocusEventSnapshot, ...]:
		pendingEvents = tuple(self._pendingEvents)
		self._pendingEvents.clear()
		return pendingEvents

	def _handleEvent(self, event, userData=None) -> None:
		del userData
		focusEvent = snapshotFocusEvent(event)
		self.latestEvent = focusEvent
		self._pendingEvents.append(focusEvent)
		if focusEvent.detail1 and focusEvent.sourceObject is not None:
			self.latestFocusedObject = focusEvent.sourceObject


def _getControlTypes():
	import controlTypes

	return controlTypes


@lru_cache(maxsize=1)
def _getAtspiRoleMap() -> dict[object, object]:
	Atspi = importAtspi()
	controlTypes = _getControlTypes()
	Role = controlTypes.Role
	return {
		Atspi.Role.ACCELERATOR_LABEL: Role.LABEL,
		Atspi.Role.ALERT: Role.ALERT,
		Atspi.Role.ANIMATION: Role.ANIMATION,
		Atspi.Role.APPLICATION: Role.APPLICATION,
		Atspi.Role.ARTICLE: Role.ARTICLE,
		Atspi.Role.AUDIO: Role.AUDIO,
		Atspi.Role.AUTOCOMPLETE: Role.COMBOBOX,
		Atspi.Role.BLOCK_QUOTE: Role.BLOCKQUOTE,
		Atspi.Role.CALENDAR: Role.CALENDAR,
		Atspi.Role.CANVAS: Role.CANVAS,
		Atspi.Role.CAPTION: Role.CAPTION,
		Atspi.Role.CHART: Role.CHART,
		Atspi.Role.CHECK_BOX: Role.CHECKBOX,
		Atspi.Role.CHECK_MENU_ITEM: Role.CHECKMENUITEM,
		Atspi.Role.COLOR_CHOOSER: Role.COLORCHOOSER,
		Atspi.Role.COLUMN_HEADER: Role.TABLECOLUMNHEADER,
		Atspi.Role.COMBO_BOX: Role.COMBOBOX,
		Atspi.Role.COMMENT: Role.COMMENT,
		Atspi.Role.CONTENT_DELETION: Role.DELETED_CONTENT,
		Atspi.Role.CONTENT_INSERTION: Role.INSERTED_CONTENT,
		Atspi.Role.DATE_EDITOR: Role.DATEEDITOR,
		Atspi.Role.DEFINITION: Role.DEFINITION,
		Atspi.Role.DESCRIPTION_LIST: Role.LIST,
		Atspi.Role.DESCRIPTION_TERM: Role.LISTITEM,
		Atspi.Role.DESCRIPTION_VALUE: Role.LISTITEM,
		Atspi.Role.DESKTOP_FRAME: Role.DESKTOPPANE,
		Atspi.Role.DESKTOP_ICON: Role.DESKTOPICON,
		Atspi.Role.DIAL: Role.DIAL,
		Atspi.Role.DIALOG: Role.DIALOG,
		Atspi.Role.DIRECTORY_PANE: Role.DIRECTORYPANE,
		Atspi.Role.DOCUMENT_EMAIL: Role.DOCUMENT,
		Atspi.Role.DOCUMENT_FRAME: Role.DOCUMENT,
		Atspi.Role.DOCUMENT_PRESENTATION: Role.DOCUMENT,
		Atspi.Role.DOCUMENT_SPREADSHEET: Role.DOCUMENT,
		Atspi.Role.DOCUMENT_TEXT: Role.DOCUMENT,
		Atspi.Role.DOCUMENT_WEB: Role.DOCUMENT,
		Atspi.Role.DRAWING_AREA: Role.CANVAS,
		Atspi.Role.EDITBAR: Role.EDITBAR,
		Atspi.Role.EMBEDDED: Role.EMBEDDEDOBJECT,
		Atspi.Role.ENTRY: Role.EDITABLETEXT,
		Atspi.Role.FILE_CHOOSER: Role.FILECHOOSER,
		Atspi.Role.FILLER: Role.FILLER,
		Atspi.Role.FONT_CHOOSER: Role.FONTCHOOSER,
		Atspi.Role.FOOTER: Role.FOOTER,
		Atspi.Role.FOOTNOTE: Role.FOOTNOTE,
		Atspi.Role.FORM: Role.FORM,
		Atspi.Role.FRAME: Role.FRAME,
		Atspi.Role.GLASS_PANE: Role.GLASSPANE,
		Atspi.Role.GROUPING: Role.GROUPING,
		Atspi.Role.HEADER: Role.HEADER,
		Atspi.Role.HEADING: Role.HEADING,
		Atspi.Role.HTML_CONTAINER: Role.DOCUMENT,
		Atspi.Role.ICON: Role.ICON,
		Atspi.Role.IMAGE: Role.GRAPHIC,
		Atspi.Role.IMAGE_MAP: Role.IMAGEMAP,
		Atspi.Role.INFO_BAR: Role.ALERT,
		Atspi.Role.INPUT_METHOD_WINDOW: Role.INPUTWINDOW,
		Atspi.Role.INTERNAL_FRAME: Role.INTERNALFRAME,
		Atspi.Role.LABEL: Role.LABEL,
		Atspi.Role.LANDMARK: Role.LANDMARK,
		Atspi.Role.LAYERED_PANE: Role.LAYEREDPANE,
		Atspi.Role.LEVEL_BAR: Role.PROGRESSBAR,
		Atspi.Role.LINK: Role.LINK,
		Atspi.Role.LIST: Role.LIST,
		Atspi.Role.LIST_BOX: Role.LIST,
		Atspi.Role.LIST_ITEM: Role.LISTITEM,
		Atspi.Role.LOG: Role.DOCUMENT,
		Atspi.Role.MARK: Role.MARKED_CONTENT,
		Atspi.Role.MARQUEE: Role.ANIMATION,
		Atspi.Role.MATH: Role.MATH,
		Atspi.Role.MATH_FRACTION: Role.MATH,
		Atspi.Role.MATH_ROOT: Role.MATH,
		Atspi.Role.MENU: Role.MENU,
		Atspi.Role.MENU_BAR: Role.MENUBAR,
		Atspi.Role.MENU_ITEM: Role.MENUITEM,
		Atspi.Role.NOTIFICATION: Role.ALERT,
		Atspi.Role.OPTION_PANE: Role.OPTIONPANE,
		Atspi.Role.PAGE: Role.PAGE,
		Atspi.Role.PAGE_TAB: Role.TAB,
		Atspi.Role.PAGE_TAB_LIST: Role.TABCONTROL,
		Atspi.Role.PANEL: Role.PANEL,
		Atspi.Role.PARAGRAPH: Role.PARAGRAPH,
		Atspi.Role.PASSWORD_TEXT: Role.PASSWORDEDIT,
		Atspi.Role.POPUP_MENU: Role.POPUPMENU,
		Atspi.Role.PROGRESS_BAR: Role.PROGRESSBAR,
		Atspi.Role.PUSH_BUTTON: Role.BUTTON,
		Atspi.Role.PUSH_BUTTON_MENU: Role.MENUBUTTON,
		Atspi.Role.RADIO_BUTTON: Role.RADIOBUTTON,
		Atspi.Role.RADIO_MENU_ITEM: Role.RADIOMENUITEM,
		Atspi.Role.RATING: Role.INDICATOR,
		Atspi.Role.REDUNDANT_OBJECT: Role.REDUNDANTOBJECT,
		Atspi.Role.ROOT_PANE: Role.ROOTPANE,
		Atspi.Role.ROW_HEADER: Role.TABLEROWHEADER,
		Atspi.Role.RULER: Role.RULER,
		Atspi.Role.SCROLL_BAR: Role.SCROLLBAR,
		Atspi.Role.SCROLL_PANE: Role.SCROLLPANE,
		Atspi.Role.SECTION: Role.SECTION,
		Atspi.Role.SEPARATOR: Role.SEPARATOR,
		Atspi.Role.SLIDER: Role.SLIDER,
		Atspi.Role.SPIN_BUTTON: Role.SPINBUTTON,
		Atspi.Role.SPLIT_PANE: Role.SPLITPANE,
		Atspi.Role.STATIC: Role.STATICTEXT,
		Atspi.Role.STATUS_BAR: Role.STATUSBAR,
		Atspi.Role.SUBSCRIPT: Role.SUBSCRIPT,
		Atspi.Role.SUGGESTION: Role.SUGGESTION,
		Atspi.Role.SUPERSCRIPT: Role.SUPERSCRIPT,
		Atspi.Role.TABLE: Role.TABLE,
		Atspi.Role.TABLE_CELL: Role.TABLECELL,
		Atspi.Role.TABLE_COLUMN_HEADER: Role.TABLECOLUMNHEADER,
		Atspi.Role.TABLE_ROW: Role.TABLEROW,
		Atspi.Role.TABLE_ROW_HEADER: Role.TABLEROWHEADER,
		Atspi.Role.TEAROFF_MENU_ITEM: Role.TEAROFFMENU,
		Atspi.Role.TERMINAL: Role.TERMINAL,
		Atspi.Role.TEXT: Role.STATICTEXT,
		Atspi.Role.TIMER: Role.CLOCK,
		Atspi.Role.TITLE_BAR: Role.TITLEBAR,
		Atspi.Role.TOGGLE_BUTTON: Role.TOGGLEBUTTON,
		Atspi.Role.TOOL_BAR: Role.TOOLBAR,
		Atspi.Role.TOOL_TIP: Role.TOOLTIP,
		Atspi.Role.TREE: Role.TREEVIEW,
		Atspi.Role.TREE_ITEM: Role.TREEVIEWITEM,
		Atspi.Role.TREE_TABLE: Role.DATAGRID,
		Atspi.Role.VIDEO: Role.VIDEO,
		Atspi.Role.VIEWPORT: Role.VIEWPORT,
		Atspi.Role.WINDOW: Role.WINDOW,
	}


@lru_cache(maxsize=1)
def _getAtspiStateMap() -> dict[object, object]:
	Atspi = importAtspi()
	controlTypes = _getControlTypes()
	State = controlTypes.State
	return {
		Atspi.StateType.BUSY: State.BUSY,
		Atspi.StateType.CHECKABLE: State.CHECKABLE,
		Atspi.StateType.CHECKED: State.CHECKED,
		Atspi.StateType.COLLAPSED: State.COLLAPSED,
		Atspi.StateType.DEFUNCT: State.DEFUNCT,
		Atspi.StateType.EDITABLE: State.EDITABLE,
		Atspi.StateType.EXPANDED: State.EXPANDED,
		Atspi.StateType.FOCUSABLE: State.FOCUSABLE,
		Atspi.StateType.FOCUSED: State.FOCUSED,
		Atspi.StateType.HAS_POPUP: State.HASPOPUP,
		Atspi.StateType.ICONIFIED: State.ICONIFIED,
		Atspi.StateType.INVALID_ENTRY: State.INVALID_ENTRY,
		Atspi.StateType.MODAL: State.MODAL,
		Atspi.StateType.MULTISELECTABLE: State.MULTISELECTABLE,
		Atspi.StateType.MULTI_LINE: State.MULTILINE,
		Atspi.StateType.PRESSED: State.PRESSED,
		Atspi.StateType.READ_ONLY: State.READONLY,
		Atspi.StateType.REQUIRED: State.REQUIRED,
		Atspi.StateType.SELECTABLE: State.SELECTABLE,
		Atspi.StateType.SELECTED: State.SELECTED,
		Atspi.StateType.STALE: State.DEFUNCT,
		Atspi.StateType.SUPPORTS_AUTOCOMPLETION: State.AUTOCOMPLETE,
		Atspi.StateType.TRUNCATED: State.CROPPED,
		Atspi.StateType.VISITED: State.VISITED,
	}


def _getAccessibleChildCount(accessible) -> int:
	if accessible is None:
		return 0
	try:
		return accessible.get_child_count()
	except Exception:
		return 0


def _getAccessibleStateSet(accessible):
	if accessible is None:
		return None
	try:
		return accessible.get_state_set()
	except Exception:
		return None


def _getFocusedState(accessible) -> bool:
	Atspi = importAtspi()
	stateSet = _getAccessibleStateSet(accessible)
	return bool(stateSet and stateSet.contains(Atspi.StateType.FOCUSED))


def _getAccessibleName(accessible) -> str | None:
	if accessible is None:
		return None
	try:
		return accessible.get_name()
	except Exception:
		return None


def _getAccessibleRole(accessible) -> str | None:
	if accessible is None:
		return None
	try:
		return accessible.get_role_name()
	except Exception:
		return None


def _getHostApplicationName(accessible) -> str | None:
	if accessible is None:
		return None
	try:
		app = accessible.get_application()
	except Exception:
		return None
	return _getAccessibleName(app)


def _normalizeRole(accessible, stateSet):
	Atspi = importAtspi()
	controlTypes = _getControlTypes()
	if accessible is None:
		return controlTypes.Role.UNKNOWN
	role = _getAtspiRoleMap().get(accessible.get_role(), controlTypes.Role.UNKNOWN)
	if accessible.get_role() == Atspi.Role.TEXT:
		if stateSet and stateSet.contains(Atspi.StateType.EDITABLE):
			return controlTypes.Role.EDITABLETEXT
		return controlTypes.Role.STATICTEXT
	return role


def _shouldExposeUnavailableState(stateSet) -> bool:
	if not stateSet:
		return False
	Atspi = importAtspi()
	return any(
		stateSet.contains(atspiState)
		for atspiState in (
			Atspi.StateType.CHECKABLE,
			Atspi.StateType.EDITABLE,
			Atspi.StateType.FOCUSABLE,
			Atspi.StateType.SELECTABLE,
			Atspi.StateType.SELECTABLE_TEXT,
		)
	)


def _shouldExposeVisibilityState(stateSet) -> bool:
	return _shouldExposeUnavailableState(stateSet)


def _normalizeStates(stateSet, role):
	Atspi = importAtspi()
	controlTypes = _getControlTypes()
	State = controlTypes.State
	states: set[State] = set()
	if stateSet:
		for atspiState, nvdaState in _getAtspiStateMap().items():
			if stateSet.contains(atspiState):
				states.add(nvdaState)
		if stateSet.contains(Atspi.StateType.INDETERMINATE):
			if role in (controlTypes.Role.CHECKBOX, controlTypes.Role.CHECKMENUITEM):
				states.add(State.HALFCHECKED)
			else:
				states.add(State.INDETERMINATE)
		if stateSet.contains(Atspi.StateType.SELECTABLE_TEXT):
			states.add(State.SELECTABLE)
		if _shouldExposeUnavailableState(stateSet) and (
			not stateSet.contains(Atspi.StateType.ENABLED)
			or not stateSet.contains(Atspi.StateType.SENSITIVE)
		):
			states.add(State.UNAVAILABLE)
		if _shouldExposeVisibilityState(stateSet):
			if not stateSet.contains(Atspi.StateType.VISIBLE):
				states.add(State.INVISIBLE)
			elif not stateSet.contains(Atspi.StateType.SHOWING):
				states.add(State.OFFSCREEN)
	if role == controlTypes.Role.LINK:
		states.add(State.LINKED)
	if role == controlTypes.Role.PASSWORDEDIT:
		states.add(State.PROTECTED)
	if role == controlTypes.Role.TOGGLEBUTTON and State.CHECKED in states:
		states.discard(State.CHECKED)
		states.add(State.PRESSED)
	role, states = controlTypes.transformRoleStates(role, states)
	return role, frozenset(states)


def snapshotAccessibleObject(accessible) -> AtspiObjectSnapshot:
	stateSet = _getAccessibleStateSet(accessible)
	role = _normalizeRole(accessible, stateSet)
	role, states = _normalizeStates(stateSet, role)
	return AtspiObjectSnapshot(
		name=_getAccessibleName(accessible),
		rawRole=_getAccessibleRole(accessible),
		role=role,
		states=states,
		childCount=_getAccessibleChildCount(accessible),
		focused=_getFocusedState(accessible),
		applicationName=_getHostApplicationName(accessible),
	)


def describeObjectSnapshot(snapshot: AtspiObjectSnapshot) -> str:
	stateNames = ",".join(snapshot.stateNames) or "-"
	return (
		f"role={snapshot.roleName} rawRole={snapshot.rawRole} "
		f"name={snapshot.name!r} app={snapshot.applicationName!r} "
		f"states={stateNames} childCount={snapshot.childCount}"
	)


def _snapshotAccessible(accessible) -> AccessibleSnapshot:
	return AccessibleSnapshot(
		name=_getAccessibleName(accessible),
		role=_getAccessibleRole(accessible),
		childCount=_getAccessibleChildCount(accessible),
		focused=_getFocusedState(accessible),
	)


def snapshotDesktop(*, maxApplications: int = 10) -> DesktopSnapshot:
	Atspi = importAtspi()
	desktopCount = Atspi.get_desktop_count()
	if desktopCount <= 0:
		return DesktopSnapshot(
			desktopCount=desktopCount,
			desktopName=None,
			rootChildCount=0,
			applications=(),
		)
	desktop = Atspi.get_desktop(0)
	rootChildCount = _getAccessibleChildCount(desktop)
	applications: list[AccessibleSnapshot] = []
	normalizedApplications: list[AtspiObjectSnapshot] = []
	for index in range(min(rootChildCount, maxApplications)):
		try:
			accessible = desktop.get_child_at_index(index)
		except Exception:
			continue
		applications.append(_snapshotAccessible(accessible))
		try:
			normalizedApplications.append(snapshotAccessibleObject(accessible))
		except Exception:
			pass
	return DesktopSnapshot(
		desktopCount=desktopCount,
		desktopName=desktop.get_name(),
		rootChildCount=rootChildCount,
		applications=tuple(applications),
		normalizedApplications=tuple(normalizedApplications),
	)


def snapshotFocusEvent(event) -> FocusEventSnapshot:
	source = getattr(event, "source", None)
	try:
		sourceObject = snapshotAccessibleObject(source) if source is not None else None
	except Exception:
		sourceObject = None
	return FocusEventSnapshot(
		eventType=getattr(event, "type", ""),
		detail1=int(getattr(event, "detail1", 0) or 0),
		detail2=int(getattr(event, "detail2", 0) or 0),
		sourceName=_getAccessibleName(source),
		sourceRole=_getAccessibleRole(source),
		hostApplicationName=_getHostApplicationName(source),
		sourceObject=sourceObject,
	)
