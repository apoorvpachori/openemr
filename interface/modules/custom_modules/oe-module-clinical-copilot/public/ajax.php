<?php

declare(strict_types=1);

/**
 * Clinical Co-Pilot — AJAX entry point
 *
 * This file is the target of every fetch() POST from the chat panel.
 *
 * Why require globals.php first?
 * globals.php bootstraps OpenEMR's entire runtime: it initialises the database
 * connection, starts the session, loads all core utilities (CsrfUtils, AclMain,
 * EventAuditLogger, SessionWrapperFactory, etc.), and sets up the autoloader.
 * Without it, none of OpenEMR's framework is available and our controller will
 * fail with "class not found" errors.
 *
 * Path breakdown from this file's location:
 *   public/          (this file)
 *   ../              oe-module-clinical-copilot/
 *   ../../           custom_modules/
 *   ../../../        modules/
 *   ../../../../     interface/     ← globals.php lives here
 *
 * @package   OpenEMR
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

require_once(__DIR__ . '/../../../../globals.php');

use OpenEMR\Modules\ClinicalCopilot\Controller\ChatController;

// Instantiate the controller and handle the request.
// ChatController::handleRequest() performs all security checks, writes the
// audit log, and returns a JSON response.
(new ChatController())->handleRequest();
