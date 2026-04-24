# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2026 NV Access Limited
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import time
from typing import Any
from xml.etree import ElementTree


@dataclass(frozen=True)
class ExportedGtkMenuItem:
	label: str | None
	action: str | None
	accel: tuple[str, ...]
	path: str
	depth: int
	hasSubmenu: bool


@dataclass(frozen=True)
class ExportedGtkMenuSnapshot:
	appId: str
	objectPaths: tuple[str, ...]
	items: tuple[ExportedGtkMenuItem, ...]


@dataclass(frozen=True)
class GtkMenuMatch:
	label: str
	path: str
	accel: tuple[str, ...]


def _normalizeText(value: Any) -> str | None:
	if value is None:
		return None
	value = " ".join(str(value).split())
	return value or None


def _normalizeShortcut(shortcut: str | None) -> str | None:
	shortcut = _normalizeText(shortcut)
	if not shortcut:
		return None
	shortcut = shortcut.replace("<Primary>", "Control+")
	shortcut = shortcut.replace("<Ctrl>", "Control+")
	shortcut = shortcut.replace("<Shift>", "Shift+")
	shortcut = shortcut.replace("<Alt>", "Alt+")
	shortcut = shortcut.replace("<Super>", "Super+")
	shortcut = shortcut.replace("<Meta>", "Meta+")
	shortcut = shortcut.replace("<", "")
	shortcut = shortcut.replace(">", "")
	shortcut = shortcut.replace("KP_", "Keypad ")
	return shortcut


def _normalizeShortcutSet(shortcuts: tuple[str, ...]) -> tuple[str, ...]:
	normalized: list[str] = []
	for shortcut in shortcuts:
		normalizedShortcut = _normalizeShortcut(shortcut)
		if normalizedShortcut and normalizedShortcut not in normalized:
			normalized.append(normalizedShortcut)
	return tuple(normalized)


def _appIdToObjectPath(appId: str) -> str:
	return "/" + appId.replace(".", "/")


@lru_cache(maxsize=1)
def _getGio():
	import gi

	from gi.repository import Gio

	return Gio


def _getSessionBusConnection():
	Gio = _getGio()
	return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def _introspectObject(busName: str, objectPath: str) -> str | None:
	Gio = _getGio()
	connection = _getSessionBusConnection()
	proxy = Gio.DBusProxy.new_sync(
		connection,
		Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
		None,
		busName,
		objectPath,
		"org.freedesktop.DBus.Introspectable",
		None,
	)
	result = proxy.call_sync(
		"Introspect",
		None,
		Gio.DBusCallFlags.NONE,
		500,
		None,
	)
	if result is None:
		return None
	return result.unpack()[0]


def _iterMenuObjectPaths(busName: str, appId: str, *, maxDepth: int = 3) -> tuple[str, ...]:
	rootPath = _appIdToObjectPath(appId) + "/menus"
	paths: list[str] = []
	visited: set[str] = set()
	pending: list[tuple[str, int]] = [(rootPath, 0)]
	while pending:
		objectPath, depth = pending.pop(0)
		if objectPath in visited or depth > maxDepth:
			continue
		visited.add(objectPath)
		try:
			xmlText = _introspectObject(busName, objectPath)
		except Exception:
			continue
		if not xmlText:
			continue
		try:
			rootNode = ElementTree.fromstring(xmlText)
		except Exception:
			continue
		interfaceNames = {
			interfaceNode.attrib.get("name", "")
			for interfaceNode in rootNode.findall("interface")
		}
		if "org.gtk.Menus" in interfaceNames or depth > 0:
			paths.append(objectPath)
		for childNode in rootNode.findall("node"):
			childName = childNode.attrib.get("name")
			if not childName:
				continue
			childPath = objectPath.rstrip("/") + "/" + childName
			pending.append((childPath, depth + 1))
	return tuple(dict.fromkeys(paths))


def _variantToPython(variant) -> Any:
	if variant is None:
		return None
	try:
		return variant.unpack()
	except Exception:
		return str(variant)


def _readMenuItemShortcuts(model, index: int) -> tuple[str, ...]:
	shortcuts: list[str] = []
	for attributeName in ("accel", "accels", "keyshortcuts"):
		attributeValue = _variantToPython(
			model.get_item_attribute_value(index, attributeName, None),
		)
		if isinstance(attributeValue, str):
			shortcuts.append(attributeValue)
		elif isinstance(attributeValue, (list, tuple)):
			for item in attributeValue:
				if isinstance(item, str):
					shortcuts.append(item)
	return _normalizeShortcutSet(tuple(shortcuts))


def _flattenMenuModel(model, objectPath: str, *, depth: int = 0) -> tuple[ExportedGtkMenuItem, ...]:
	items: list[ExportedGtkMenuItem] = []
	itemCount = int(model.get_n_items() or 0)
	for index in range(itemCount):
		label = _normalizeText(
			_variantToPython(model.get_item_attribute_value(index, "label", None)),
		)
		action = _normalizeText(
			_variantToPython(model.get_item_attribute_value(index, "action", None)),
		)
		accel = _readMenuItemShortcuts(model, index)
		submenuModel = model.get_item_link(index, "submenu")
		sectionModel = model.get_item_link(index, "section")
		hasSubmenu = submenuModel is not None
		items.append(
			ExportedGtkMenuItem(
				label=label,
				action=action,
				accel=accel,
				path=f"{objectPath}#{depth}:{index}",
				depth=depth,
				hasSubmenu=hasSubmenu,
			),
		)
		if sectionModel is not None:
			items.extend(_flattenMenuModel(sectionModel, objectPath, depth=depth + 1))
		if submenuModel is not None:
			items.extend(_flattenMenuModel(submenuModel, objectPath, depth=depth + 1))
	return tuple(items)


def snapshotExportedGtkMenus(appId: str, *, busName: str | None = None) -> ExportedGtkMenuSnapshot | None:
	busName = busName or appId
	connection = _getSessionBusConnection()
	Gio = _getGio()
	objectPaths = _iterMenuObjectPaths(busName, appId)
	if not objectPaths:
		return None
	items: list[ExportedGtkMenuItem] = []
	for objectPath in objectPaths:
		try:
			menuModel = Gio.DBusMenuModel.get(connection, busName, objectPath)
		except Exception:
			continue
		if menuModel is None:
			continue
		items.extend(_flattenMenuModel(menuModel, objectPath))
	if not items:
		return None
	return ExportedGtkMenuSnapshot(
		appId=appId,
		objectPaths=objectPaths,
		items=tuple(items),
	)


_snapshotCache: dict[tuple[str, str], tuple[float, ExportedGtkMenuSnapshot | None]] = {}


def getExportedGtkMenuSnapshot(
	appId: str,
	*,
	busName: str | None = None,
	cacheTtlSeconds: float = 0.75,
) -> ExportedGtkMenuSnapshot | None:
	busName = busName or appId
	cacheKey = (appId, busName)
	now = time.monotonic()
	cached = _snapshotCache.get(cacheKey)
	if cached and now - cached[0] <= cacheTtlSeconds:
		return cached[1]
	snapshot = snapshotExportedGtkMenus(appId, busName=busName)
	_snapshotCache[cacheKey] = (now, snapshot)
	return snapshot


def matchExportedGtkMenuItem(
	appId: str,
	*,
	keyshortcuts: str | None,
	hasSubmenu: bool | None = None,
	busName: str | None = None,
) -> GtkMenuMatch | None:
	normalizedShortcut = _normalizeShortcut(keyshortcuts)
	if not normalizedShortcut:
		return None
	snapshot = getExportedGtkMenuSnapshot(appId, busName=busName)
	if snapshot is None:
		return None
	matches = [
		item
		for item in snapshot.items
		if item.label
		and normalizedShortcut in item.accel
		and (hasSubmenu is None or item.hasSubmenu == hasSubmenu)
	]
	if len(matches) != 1:
		return None
	match = matches[0]
	return GtkMenuMatch(
		label=match.label,
		path=match.path,
		accel=match.accel,
	)


def describeExportedGtkMenus(snapshot: ExportedGtkMenuSnapshot | None, *, maxItems: int = 24) -> str:
	if snapshot is None:
		return "no exported GTK menus"
	itemDescriptions = [
		f"{item.label!r}:{item.accel}:{item.action}:{'submenu' if item.hasSubmenu else '-'}"
		for item in snapshot.items[:maxItems]
	]
	return (
		f"paths={snapshot.objectPaths!r} "
		f"items=[{', '.join(itemDescriptions)}]"
	)
