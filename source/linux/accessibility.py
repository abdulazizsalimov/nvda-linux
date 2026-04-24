# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
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
	eventLabel: str
	shouldAnnounce: bool
	detail1: int
	detail2: int
	nameOverride: str | None
	sourceName: str | None
	sourceRole: str | None
	hostApplicationName: str | None
	sourceObject: AtspiObjectSnapshot | None = None
	sourceAccessible: object | None = None
	debugNameSources: str | None = None


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
		self.latestFocusedAccessible: object | None = None

	@property
	def registeredEvents(self) -> tuple[str, ...]:
		return self._registeredEvents

	@property
	def pendingEventCount(self) -> int:
		return len(self._pendingEvents)

	def register(self, *eventTypes: str) -> tuple[str, ...]:
		if not eventTypes:
			eventTypes = (
				"object:state-changed:focused",
				"object:active-descendant-changed",
				"object:selection-changed",
				"object:state-changed:selected",
				"object:property-change:accessible-name",
				"object:attributes-changed",
			)
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
		if focusEvent.shouldAnnounce and focusEvent.sourceObject is not None:
			self.latestFocusedObject = focusEvent.sourceObject
			self.latestFocusedAccessible = focusEvent.sourceAccessible


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


def _clearAccessibleCache(accessible) -> bool:
	if accessible is None:
		return False
	for methodName in ("clear_cache", "clear_cache_single"):
		method = getattr(accessible, methodName, None)
		if not callable(method):
			continue
		try:
			method()
		except Exception:
			continue
		return True
	return False


def clearAccessibleCache(accessible) -> bool:
	return _clearAccessibleCache(accessible)


def _getAccessibleRoleEnum(accessible):
	if accessible is None:
		return None
	try:
		return accessible.get_role()
	except Exception:
		return None


def _getFocusedState(accessible) -> bool:
	Atspi = importAtspi()
	stateSet = _getAccessibleStateSet(accessible)
	return bool(stateSet and stateSet.contains(Atspi.StateType.FOCUSED))


def _normalizeAccessibleName(name: str | None) -> str | None:
	if not name:
		return None
	name = " ".join(str(name).split())
	return name or None


def _callAccessibleStringMethod(accessible, methodName: str) -> str | None:
	if accessible is None:
		return None
	method = getattr(accessible, methodName, None)
	if not callable(method):
		return None
	try:
		return _normalizeAccessibleName(method())
	except Exception:
		return None


def _getAccessibleSelfName(accessible) -> str | None:
	return _callAccessibleStringMethod(accessible, "get_name")


def _getAccessibleDescription(accessible) -> str | None:
	return _callAccessibleStringMethod(accessible, "get_description")


def _getAccessibleHelpText(accessible) -> str | None:
	return _callAccessibleStringMethod(accessible, "get_help_text")


def _getAccessibleId(accessible) -> str | None:
	return _callAccessibleStringMethod(accessible, "get_accessible_id")


def _getAccessibleChild(accessible, index: int):
	if accessible is None:
		return None
	try:
		return accessible.get_child_at_index(index)
	except Exception:
		return None


def _getAccessibleParent(accessible):
	if accessible is None:
		return None
	try:
		return accessible.get_parent()
	except Exception:
		return None


def _iterAccessibleDescendants(
	accessible,
	*,
	maxDepth: int = 3,
	maxNodes: int = 32,
	maxChildrenPerNode: int = 16,
):
	if accessible is None or maxDepth <= 0 or maxNodes <= 0:
		return
	pending: deque[tuple[object, int]] = deque([(accessible, 0)])
	visited = 0
	while pending and visited < maxNodes:
		node, depth = pending.popleft()
		if depth >= maxDepth:
			continue
		childCount = min(_getAccessibleChildCount(node), maxChildrenPerNode)
		for childIndex in range(childCount):
			child = _getAccessibleChild(node, childIndex)
			if child is None:
				continue
			visited += 1
			yield child
			if visited >= maxNodes:
				return
			pending.append((child, depth + 1))


def _isUsableAccessibleNameCandidate(
	name: str | None,
	*,
	applicationName: str | None,
) -> bool:
	if not name:
		return False
	if applicationName and name.casefold() == applicationName.casefold():
		return False
	return True


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
			if rawAttributes:
				parsedAttributes: list[tuple[str, str]] = []
				for rawAttribute in rawAttributes:
					rawAttribute = str(rawAttribute)
					if ":" in rawAttribute:
						key, value = rawAttribute.split(":", 1)
					elif "=" in rawAttribute:
						key, value = rawAttribute.split("=", 1)
					else:
						continue
					key = key.strip()
					value = _normalizeAccessibleName(value)
					if key and value:
						parsedAttributes.append((key, value))
				if parsedAttributes:
					return tuple(parsedAttributes)
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
	parsedAttributes = []
	for item in items:
		if not isinstance(item, tuple) or len(item) != 2:
			continue
		key, value = item
		key = str(key).strip()
		value = _normalizeAccessibleName(value)
		if key and value:
			parsedAttributes.append((key, value))
	return tuple(parsedAttributes)


def getAccessibleAttributes(accessible) -> tuple[tuple[str, str], ...]:
	return _getAccessibleAttributes(accessible)


def getAccessibleAttributeValue(accessible, attributeName: str) -> str | None:
	attributeKey = attributeName.casefold()
	for key, value in _getAccessibleAttributes(accessible):
		if key.casefold() == attributeKey:
			return value
	return None


def replaceObjectSnapshotName(
	snapshot: AtspiObjectSnapshot,
	name: str,
) -> AtspiObjectSnapshot:
	return replace(snapshot, name=_normalizeAccessibleName(name))


def _iterAccessibleAttributeCandidates(
	accessible,
	*,
	applicationName: str | None,
) -> tuple[str, ...]:
	preferredKeys = (
		"accessible-name",
		"label",
		"displayed-label",
		"displayed_text",
		"displayed-text",
		"title",
		"tooltip-text",
		"placeholder-text",
		"description",
	)
	attributeMap = dict(_getAccessibleAttributes(accessible))
	candidates: list[str] = []
	seen: set[str] = set()

	def _addCandidate(candidate: str | None) -> None:
		if not _isUsableAccessibleNameCandidate(candidate, applicationName=applicationName):
			return
		candidate = candidate.strip()
		candidateKey = candidate.casefold()
		if candidateKey in seen:
			return
		seen.add(candidateKey)
		candidates.append(candidate)

	for key in preferredKeys:
		_addCandidate(attributeMap.get(key))
	for key, value in attributeMap.items():
		keyLower = key.casefold()
		if "label" in keyLower or "name" in keyLower or "title" in keyLower:
			_addCandidate(value)
	return tuple(candidates)


def _getAccessibleIdCandidate(
	accessible,
	*,
	applicationName: str | None,
) -> str | None:
	accessibleId = _getAccessibleId(accessible)
	if not accessibleId:
		return None
	if applicationName and accessibleId.casefold() == applicationName.casefold():
		return None
	if any(separator in accessibleId for separator in (".", "/", "::")):
		return None
	if len(accessibleId) > 48:
		return None
	if not any(character.isalpha() for character in accessibleId):
		return None
	normalizedId = _normalizeAccessibleName(accessibleId.replace("_", " ").replace("-", " "))
	if not _isUsableAccessibleNameCandidate(normalizedId, applicationName=applicationName):
		return None
	return normalizedId


def _getAccessibleActionMetadata(accessible) -> tuple[str, ...]:
	if accessible is None:
		return ()
	getActionCount = getattr(accessible, "get_n_actions", None)
	if not callable(getActionCount):
		return ()
	try:
		actionCount = min(int(getActionCount() or 0), 4)
	except Exception:
		return ()
	if actionCount <= 0:
		return ()
	actionMetadata: list[str] = []
	for actionIndex in range(actionCount):
		actionBits: list[str] = []
		for methodName in ("get_localized_name", "get_action_name", "get_action_description"):
			method = getattr(accessible, methodName, None)
			if not callable(method):
				continue
			try:
				value = _normalizeAccessibleName(method(actionIndex))
			except Exception:
				value = None
			if value:
				actionBits.append(f"{methodName}={value!r}")
		if actionBits:
			actionMetadata.append(f"{actionIndex}:{{{', '.join(actionBits)}}}")
	return tuple(actionMetadata)


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
		return _normalizeAccessibleName(getText(0, characterCount))
	except Exception:
		try:
			return _normalizeAccessibleName(getText(0, -1))
		except Exception:
			return None


def _normalizeEventString(value) -> str | None:
	if not isinstance(value, str):
		return None
	return _normalizeAccessibleName(value)


def _isAccessibleLike(value) -> bool:
	if value is None:
		return False
	return any(
		callable(getattr(value, methodName, None))
		for methodName in (
			"get_name",
			"get_role",
			"get_application",
			"get_role_name",
		)
	)


def _getAccessibleSelectionIface(accessible):
	if accessible is None:
		return None
	getSelectionIface = getattr(accessible, "get_selection_iface", None)
	if callable(getSelectionIface):
		try:
			selectionIface = getSelectionIface()
		except Exception:
			selectionIface = None
		else:
			if selectionIface is not None:
				return selectionIface
	isSelection = getattr(accessible, "is_selection", None)
	try:
		if callable(isSelection) and isSelection():
			return accessible
	except Exception:
		pass
	return None


def _getSelectedAccessibleChild(accessible):
	selectionIface = _getAccessibleSelectionIface(accessible)
	if selectionIface is not None:
		getSelectedChildCount = getattr(selectionIface, "get_n_selected_children", None)
		getSelectedChild = getattr(selectionIface, "get_selected_child", None)
		if callable(getSelectedChildCount) and callable(getSelectedChild):
			try:
				selectedChildCount = min(int(getSelectedChildCount() or 0), 8)
			except Exception:
				selectedChildCount = 0
			for childIndex in range(max(0, selectedChildCount)):
				try:
					child = getSelectedChild(childIndex)
				except Exception:
					continue
				if child is not None and child is not accessible:
					return child
	Atspi = importAtspi()
	childCount = min(_getAccessibleChildCount(accessible), 16)
	for childIndex in range(max(0, childCount)):
		child = _getAccessibleChild(accessible, childIndex)
		if child is None:
			continue
		stateSet = _getAccessibleStateSet(child)
		if not stateSet:
			continue
		try:
			if (
				stateSet.contains(Atspi.StateType.SELECTED)
				or stateSet.contains(Atspi.StateType.FOCUSED)
			):
				return child
		except Exception:
			continue
	return None


def _getActiveDescendantAccessible(event):
	anyData = getattr(event, "any_data", None)
	if _isAccessibleLike(anyData):
		return anyData
	return None


def _normalizePresentationAccessible(accessible):
	if accessible is None:
		return None
	Atspi = importAtspi()
	presentationalLeafRoles = {
		Atspi.Role.FILLER,
		Atspi.Role.LABEL,
		Atspi.Role.PANEL,
		Atspi.Role.STATIC,
		Atspi.Role.TEXT,
	}
	interactiveAncestorRoles = {
		Atspi.Role.CHECK_MENU_ITEM,
		Atspi.Role.LIST_ITEM,
		Atspi.Role.MENU,
		Atspi.Role.MENU_ITEM,
		Atspi.Role.PAGE_TAB,
		Atspi.Role.POPUP_MENU,
		Atspi.Role.PUSH_BUTTON,
		Atspi.Role.PUSH_BUTTON_MENU,
		Atspi.Role.RADIO_MENU_ITEM,
		Atspi.Role.TEAROFF_MENU_ITEM,
		Atspi.Role.TOGGLE_BUTTON,
		Atspi.Role.TREE_ITEM,
	}
	roleEnum = _getAccessibleRoleEnum(accessible)
	if roleEnum not in presentationalLeafRoles:
		return accessible
	parent = _getAccessibleParent(accessible)
	depth = 0
	while parent is not None and depth < 4:
		parentRole = _getAccessibleRoleEnum(parent)
		if parentRole in interactiveAncestorRoles:
			return parent
		parent = _getAccessibleParent(parent)
		depth += 1
	return accessible


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
		getRelation = getattr(relationSet, "get_relation", None)
		getRelationCount = getattr(relationSet, "get_n_relations", None)
		if callable(getRelation) and callable(getRelationCount):
			try:
				relationCount = int(getRelationCount() or 0)
			except Exception:
				relationCount = 0
			for relationIndex in range(max(0, relationCount)):
				try:
					relation = getRelation(relationIndex)
				except Exception:
					continue
				if relation is not None:
					relations.append(relation)
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
		if callable(getTarget):
			try:
				targets = getTarget()
			except TypeError:
				targets = None
			except Exception:
				targets = None
			else:
				if targets is not None:
					try:
						for target in targets:
							if target is None:
								continue
							yield target
							targetCount += 1
							if targetCount >= maxTargets:
								return
						continue
					except TypeError:
						pass
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


def _iterFallbackNameCandidates(
	accessible,
	*,
	applicationName: str | None,
	includeRelations: bool = True,
) -> tuple[str, ...]:
	Atspi = importAtspi()
	candidates: list[str] = []
	seen: set[str] = set()

	def _addCandidate(candidate: str | None) -> None:
		if not _isUsableAccessibleNameCandidate(candidate, applicationName=applicationName):
			return
		candidate = candidate.strip()
		candidateKey = candidate.casefold()
		if candidateKey in seen:
			return
		seen.add(candidateKey)
		candidates.append(candidate)

	_addCandidate(_getAccessibleSelfName(accessible))
	_addCandidate(_getAccessibleDescription(accessible))
	_addCandidate(_getAccessibleHelpText(accessible))
	_addCandidate(_getAccessibleTextContent(accessible))
	for candidate in _iterAccessibleAttributeCandidates(
		accessible,
		applicationName=applicationName,
	):
		_addCandidate(candidate)
	_addCandidate(_getAccessibleIdCandidate(accessible, applicationName=applicationName))
	if includeRelations:
		relationTypes = {
			getattr(Atspi.RelationType, "LABELLED_BY", None),
			getattr(Atspi.RelationType, "DESCRIBED_BY", None),
			getattr(Atspi.RelationType, "DETAILS", None),
			getattr(Atspi.RelationType, "ERROR_MESSAGE", None),
		}
		relationTypes.discard(None)
		for relatedAccessible in _iterRelationTargets(
			accessible,
			relationTypes=relationTypes,
		):
			for candidate in _iterFallbackNameCandidates(
				relatedAccessible,
				applicationName=applicationName,
				includeRelations=False,
			):
				_addCandidate(candidate)
	return tuple(candidates)


def _describeAccessibleDebugNode(
	accessible,
	*,
	applicationName: str | None,
	depth: int,
	maxDepth: int,
	maxChildrenPerNode: int,
) -> str:
	nodeRole = _getAccessibleRole(accessible)
	nodeName = _getAccessibleSelfName(accessible)
	nodeDescription = _getAccessibleDescription(accessible)
	nodeText = _getAccessibleTextContent(accessible)
	nodeId = _getAccessibleId(accessible)
	nodeAttributes = _getAccessibleAttributes(accessible)
	nodeActionMetadata = _getAccessibleActionMetadata(accessible)
	nodeCandidates = _iterFallbackNameCandidates(
		accessible,
		applicationName=applicationName,
		includeRelations=False,
	)
	childCount = _getAccessibleChildCount(accessible)
	parts = [
		f"role={nodeRole}",
		f"name={nodeName!r}",
		f"desc={nodeDescription!r}",
		f"text={nodeText!r}",
		f"id={nodeId!r}",
		f"candidates={nodeCandidates!r}",
		f"attrs={nodeAttributes!r}",
	]
	if nodeActionMetadata:
		parts.append(f"actions={nodeActionMetadata!r}")
	if depth >= maxDepth or childCount <= 0:
		return "{" + " ".join(parts) + "}"
	children: list[str] = []
	for childIndex in range(min(childCount, maxChildrenPerNode)):
		child = _getAccessibleChild(accessible, childIndex)
		if child is None:
			continue
		children.append(
			f"{childIndex}:"
			+ _describeAccessibleDebugNode(
				child,
				applicationName=applicationName,
				depth=depth + 1,
				maxDepth=maxDepth,
				maxChildrenPerNode=maxChildrenPerNode,
			)
		)
	if children:
		parts.append(f"children=[{', '.join(children)}]")
	return "{" + " ".join(parts) + "}"


def describeAccessibleNameSources(
	accessible,
	*,
	maxDepth: int = 3,
	maxChildrenPerNode: int = 4,
) -> str:
	applicationName = _getHostApplicationName(accessible)
	return (
		f"app={applicationName!r} "
		+ _describeAccessibleDebugNode(
			accessible,
			applicationName=applicationName,
			depth=0,
			maxDepth=maxDepth,
			maxChildrenPerNode=maxChildrenPerNode,
		)
	)


def _shouldUseDescendantNameFallback(
	name: str | None,
	*,
	roleEnum,
	applicationName: str | None,
) -> bool:
	if not name:
		return True
	if roleEnum is None:
		return False
	Atspi = importAtspi()
	menuLikeRoles = {
		Atspi.Role.CHECK_MENU_ITEM,
		Atspi.Role.MENU,
		Atspi.Role.MENU_ITEM,
		Atspi.Role.POPUP_MENU,
		Atspi.Role.RADIO_MENU_ITEM,
		Atspi.Role.TEAROFF_MENU_ITEM,
	}
	if roleEnum not in menuLikeRoles:
		return False
	if applicationName and name.casefold() == applicationName.casefold():
		return True
	return name.startswith("org.") or name.endswith(".desktop")


def _getDescendantAccessibleName(
	accessible,
	*,
	applicationName: str | None,
) -> str | None:
	Atspi = importAtspi()
	primaryRoles = {
		Atspi.Role.LABEL,
		Atspi.Role.PARAGRAPH,
		Atspi.Role.STATIC,
		Atspi.Role.TEXT,
	}
	secondaryRoles = {
		Atspi.Role.ACCELERATOR_LABEL,
	}
	fallbackName: str | None = None
	secondaryFallbackName: str | None = None
	for descendant in _iterAccessibleDescendants(accessible):
		descendantCandidates = _iterFallbackNameCandidates(
			descendant,
			applicationName=applicationName,
			includeRelations=False,
		)
		if not descendantCandidates:
			continue
		descendantName = descendantCandidates[0]
		descendantRole = _getAccessibleRoleEnum(descendant)
		if descendantRole in primaryRoles:
			return descendantName
		if descendantRole in secondaryRoles and secondaryFallbackName is None:
			secondaryFallbackName = descendantName
			continue
		if fallbackName is None:
			fallbackName = descendantName
	return fallbackName or secondaryFallbackName


def _getAccessibleName(accessible) -> str | None:
	if accessible is None:
		return None
	applicationName = _getHostApplicationName(accessible)
	fallbackCandidates = _iterFallbackNameCandidates(
		accessible,
		applicationName=applicationName,
	)
	name = fallbackCandidates[0] if fallbackCandidates else None
	roleEnum = _getAccessibleRoleEnum(accessible)
	if not _shouldUseDescendantNameFallback(
		name,
		roleEnum=roleEnum,
		applicationName=applicationName,
	):
		return name
	descendantName = _getDescendantAccessibleName(
		accessible,
		applicationName=applicationName,
	)
	return descendantName or name


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
	return _getAccessibleSelfName(app)


def _normalizeRole(accessible, stateSet):
	Atspi = importAtspi()
	controlTypes = _getControlTypes()
	if accessible is None:
		return controlTypes.Role.UNKNOWN
	roleEnum = _getAccessibleRoleEnum(accessible)
	role = _getAtspiRoleMap().get(roleEnum, controlTypes.Role.UNKNOWN)
	if roleEnum == Atspi.Role.TEXT:
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
		# GTK / AT-SPI often omits one of ENABLED/SENSITIVE for perfectly usable controls.
		# Treat controls as unavailable only when both are absent to avoid false positives
		# like "Home unavailable folder" in Files.
		if _shouldExposeUnavailableState(stateSet) and (
			not stateSet.contains(Atspi.StateType.ENABLED)
			and not stateSet.contains(Atspi.StateType.SENSITIVE)
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


def resolveAccessibleObjectSnapshot(
	accessible,
	*,
	attempts: int = 5,
	delaySeconds: float = 0.03,
	settleCallback=None,
	shouldContinue=None,
) -> AtspiObjectSnapshot | None:
	if accessible is None:
		return None
	import time

	try:
		snapshot = snapshotAccessibleObject(accessible)
	except Exception:
		return None
	if snapshot.name or snapshot.childCount <= 0 or attempts <= 1:
		return snapshot
	for _attempt in range(max(0, attempts - 1)):
		if callable(shouldContinue) and not shouldContinue():
			break
		_clearAccessibleCache(accessible)
		if callable(settleCallback):
			try:
				settleCallback()
			except Exception:
				pass
		if delaySeconds > 0:
			time.sleep(delaySeconds)
			if callable(settleCallback):
				try:
					settleCallback()
				except Exception:
					pass
		try:
			snapshot = snapshotAccessibleObject(accessible)
		except Exception:
			continue
		if snapshot.name:
			break
	return snapshot


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
	eventType = getattr(event, "type", "") or ""
	source = getattr(event, "source", None)
	eventLabel = eventType or "event"
	shouldAnnounce = False
	nameOverride = None
	target = source
	if eventType.startswith("object:state-changed:focused"):
		eventLabel = "focus-gained" if int(getattr(event, "detail1", 0) or 0) else "focus-lost"
		shouldAnnounce = bool(int(getattr(event, "detail1", 0) or 0))
	elif eventType.startswith("object:active-descendant-changed"):
		eventLabel = "active-descendant-changed"
		target = _getActiveDescendantAccessible(event) or source
		shouldAnnounce = target is not None
	elif eventType.startswith("object:selection-changed"):
		eventLabel = "selection-changed"
		target = _getSelectedAccessibleChild(source) or source
		shouldAnnounce = target is not None and target is not source
	elif eventType.startswith("object:state-changed:selected"):
		eventLabel = "selected" if int(getattr(event, "detail1", 0) or 0) else "deselected"
		target = source
		shouldAnnounce = bool(int(getattr(event, "detail1", 0) or 0))
	elif eventType.startswith("object:property-change:accessible-name"):
		eventLabel = "name-changed"
		nameOverride = _normalizeEventString(getattr(event, "any_data", None))
		target = source
		shouldAnnounce = bool(nameOverride)
	elif eventType.startswith("object:attributes-changed"):
		eventLabel = "attributes-changed"
		target = source
	source = _normalizePresentationAccessible(target)
	try:
		sourceObject = snapshotAccessibleObject(source) if source is not None else None
	except Exception:
		sourceObject = None
	try:
		debugNameSources = (
			describeAccessibleNameSources(source)
			if sourceObject is not None
			and sourceObject.name is None
			and sourceObject.childCount > 0
			else None
		)
	except Exception:
		debugNameSources = None
	return FocusEventSnapshot(
		eventType=eventType,
		eventLabel=eventLabel,
		shouldAnnounce=shouldAnnounce,
		detail1=int(getattr(event, "detail1", 0) or 0),
		detail2=int(getattr(event, "detail2", 0) or 0),
		nameOverride=nameOverride,
		sourceName=_getAccessibleName(source),
		sourceRole=_getAccessibleRole(source),
		hostApplicationName=_getHostApplicationName(source),
		sourceObject=sourceObject,
		sourceAccessible=source,
		debugNameSources=debugNameSources,
	)
