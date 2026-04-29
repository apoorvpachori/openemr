<?php

declare(strict_types=1);

/**
 * Clinical Co-Pilot Module Bootstrap
 *
 * OpenEMR's module loader (ModulesApplication::loadCustomModule) automatically
 * runs this file for every module that has mod_active=1 in the modules table.
 * It injects two variables into this scope before including the file:
 *
 *   $classLoader   — ModulesClassLoader, used to register PSR-4 namespaces
 *   $eventDispatcher — Symfony EventDispatcherInterface, used to subscribe to events
 *
 * @package   OpenEMR
 * @link      https://www.open-emr.org
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

// We declare the namespace here so that "new Bootstrap(...)" below resolves to
// OpenEMR\Modules\ClinicalCopilot\Bootstrap without needing an explicit use statement.
namespace OpenEMR\Modules\ClinicalCopilot;

use OpenEMR\Core\OEGlobalsBag;

/**
 * @global \OpenEMR\Core\ModulesClassLoader $classLoader  — injected by module loader
 * @global \Symfony\Component\EventDispatcher\EventDispatcherInterface $eventDispatcher — injected by module loader
 */

// Register our src/ directory under the OpenEMR\Modules\ClinicalCopilot\ namespace.
// This must happen BEFORE "new Bootstrap(...)" so the autoloader can find the class.
$classLoader->registerNamespaceIfNotExists(
    'OpenEMR\\Modules\\ClinicalCopilot\\',
    __DIR__ . DIRECTORY_SEPARATOR . 'src'
);

// Instantiate our Bootstrap class and subscribe to OpenEMR events.
// Bootstrap::subscribeToEvents() registers our chat panel on EVENT_BODY_RENDER_POST.
$bootstrap = new Bootstrap($eventDispatcher, OEGlobalsBag::getInstance()->getKernel());
$bootstrap->subscribeToEvents();
