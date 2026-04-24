#!/usr/bin/env python3
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2006-2025 NV Access Limited, Aleksey Sadovoy, Babbage B.V., Joseph Lee, Łukasz Golonka,
# Cyrille Bougot
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

"""The NVDA launcher - main / entry point into NVDA.
It can handle some command-line arguments (including help).
It sets up logging, and then starts the core.
"""

import logging
import sys
import os
import platform

from typing import Any

import globalVars
from argsParsing import getParser
import monkeyPatches
import NVDAState
import systemPlatform

#: logger to use before the true NVDA log is initialised.
# Ideally, all logging would be captured by the NVDA log, however this would introduce contention
# when multiple NVDA processes run simultaneously.
_log = logging.Logger(name="preStartup", level=logging.INFO)
_log.addHandler(logging.NullHandler(level=logging.INFO))

currentPlatform = systemPlatform.getPlatform()
currentPlatform.apply_early_monkey_patches(monkeyPatches)
appDir = currentPlatform.resolve_app_dir(
	running_as_source=NVDAState.isRunningAsSource(),
	module_path=__file__,
)

os.chdir(appDir)
globalVars.appDir = appDir
globalVars.appPid = os.getpid()

_parser = getParser()
(globalVars.appArgs, globalVars.unknownAppArgs) = _parser.parse_known_args()
# Make any app args path values absolute
# So as to not be affected by the current directory changing during process lifetime.
pathAppArgs = [
	"configPath",
	"logFileName",
	"portablePath",
]
for name in pathAppArgs:
	origVal = getattr(globalVars.appArgs, name)
	if isinstance(origVal, str):
		newVal = os.path.abspath(origVal)
		setattr(globalVars.appArgs, name, newVal)


import config  # noqa: E402
import logHandler  # noqa: E402
from logHandler import log  # noqa: E402

config.isAppX = currentPlatform.detect_is_appx()

NVDAState._initializeStartTime()

currentPlatform.ensure_supported_os()


def __getattr__(attrName: str) -> Any:
	"""Module level `__getattr__` used to preserve backward compatibility."""
	if NVDAState._allowDeprecatedAPI():
		if attrName in ("NoConsoleOptionParser", "stringToBool", "stringToLang"):
			import argsParsing

			log.warning(f"__main__.{attrName} is deprecated, use argsParsing.{attrName} instead.")
			return getattr(argsParsing, attrName)
		if attrName == "parser":
			import argsParsing

			log.warning(f"__main__.{attrName} is deprecated, use argsParsing.getParser() instead.")
			return argsParsing.getParser()
	raise AttributeError(f"module {repr(__name__)} has no attribute {repr(attrName)}")

# Handle running multiple instances of NVDA
oldAppWindowHandle = currentPlatform.find_running_instance(_log, "wxWindowClassNR", "NVDA")

if oldAppWindowHandle and not globalVars.appArgs.easeOfAccess:
	_log.debug(f"NVDA already running. OldAppWindowHandle: {oldAppWindowHandle}")
	if globalVars.appArgs.check_running:
		# NVDA is running.
		_log.debug("Is running check complete: NVDA is running.")
		_log.debug("Exiting")
		sys.exit(0)
	try:
		_log.debug(f"Terminating oldAppWindowHandle: {oldAppWindowHandle}")
		currentPlatform.terminate_running_instance(oldAppWindowHandle)
	except Exception as e:
		currentPlatform.show_error(
			"Error",
			f"Couldn't terminate existing NVDA process, abandoning start:\nException: {e}",
		)

if globalVars.appArgs.quit or (oldAppWindowHandle and globalVars.appArgs.easeOfAccess):
	_log.debug("Quitting")
	sys.exit(0)
elif globalVars.appArgs.check_running:
	# NVDA is not running.
	_log.debug("Is running check: NVDA is not running")
	_log.debug("Exiting")
	sys.exit(1)


# Ensure multiple instances are not fully started by using a mutex
desktopName = currentPlatform.get_desktop_name()
_log.info(f"DesktopName: {desktopName}")


if NVDAState._forceSecureModeEnabled():
	globalVars.appArgs.secure = True


isSecureDesktop = currentPlatform.is_running_on_secure_desktop()
currentPlatform.apply_secure_desktop_policy(
	app_args=globalVars.appArgs,
	is_secure_desktop=isSecureDesktop,
	service_debug_enabled=NVDAState._serviceDebugEnabled(),
	sys_prefix=sys.prefix,
)


try:
	mutex = currentPlatform.acquire_single_instance_mutex(desktopName, _log)
except Exception as e:
	_log.error(f"Unable to acquire mutex: {e}")
	sys.exit(1)
if mutex is None:
	_log.error("Unknown mutex acquisition error. Exiting")
	sys.exit(1)

# os.environ['PYCHECKER']="--limit 10000 -q --changetypes"
# import pychecker.checker

corePrepared = False
try:
	# Initial logging and logging code
	# #8516: because config manager isn't ready yet, we must let start and exit messages be logged unless disabled via --no-logging switch.
	# However, do log things if debug logging or log level other than 0 (not set) is requested from command line switches.
	_log = None
	logHandler.initialize()
	if logHandler.log.getEffectiveLevel() is log.DEBUG:
		log.debug("Provided arguments: {}".format(sys.argv[1:]))
	import buildVersion  # noqa: E402

	processArchitecture = os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine() or "unknown"
	log.info(f"Starting NVDA version {buildVersion.version} {processArchitecture}")
	log.debug("Debug level logging enabled")
	currentPlatform.prepare_for_core(
		app_args=globalVars.appArgs,
		is_secure_desktop=isSecureDesktop,
		is_appx=config.isAppX,
		log=log,
	)
	corePrepared = True
	import core

	core.main()
except SystemExit:
	raise
except:  # noqa: E722
	log.critical("core failure", exc_info=True)
	sys.exit(1)
finally:
	if corePrepared:
		currentPlatform.cleanup_after_core(
			app_args=globalVars.appArgs,
			is_secure_desktop=isSecureDesktop,
			is_appx=config.isAppX,
			log=log,
		)
	currentPlatform.release_single_instance_mutex(mutex, log)

log.info("NVDA exit")
sys.exit(NVDAState._getExitCode())
