<?php

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot;

use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Events\Main\Tabs\RenderEvent;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

/**
 * Subscribes to OpenEMR events and injects the chat panel into the patient chart.
 */
class Bootstrap
{
    // URL path to our ajax.php endpoint, built from the site's webroot
    private string $ajaxUrl;

    public function __construct(
        private readonly EventDispatcherInterface $eventDispatcher,
        // Kernel is accepted for consistency with other modules but not used in MVP.
        // It will be needed later for accessing services from the DI container.
        private readonly mixed $kernel
    ) {
        $webRoot = OEGlobalsBag::getInstance()->getWebRoot();
        $this->ajaxUrl = $webRoot
            . '/interface/modules/custom_modules/oe-module-clinical-copilot/public/ajax.php';
    }

    public function subscribeToEvents(): void
    {
        // EVENT_BODY_RENDER_POST fires at the very end of </body> in
        // interface/main/tabs/main.php — the outer persistent frame that wraps
        // all patient chart tabs. Anything echoed here appears on every page
        // within the patient chart without modifying any core OpenEMR files.
        $this->eventDispatcher->addListener(
            RenderEvent::EVENT_BODY_RENDER_POST,
            [$this, 'injectChatPanel']
        );
    }

    /**
     * Echoes the chat panel HTML, CSS, and JavaScript directly into the page.
     *
     * Why inline styles and scripts instead of separate files?
     * Separate asset files would require knowing the correct CDN/webroot URL at
     * build time and dealing with cache-busting. For an MVP module, inlining is
     * simpler and just as functional. We can extract to separate files later.
     */
    public function injectChatPanel(RenderEvent $event): void
    {
        // PHP variable available to the inline <script> block below via json_encode.
        // json_encode is used (not string interpolation) to safely escape the URL
        // and produce a valid JS string literal.
        $ajaxUrl = $this->ajaxUrl;
        ?>
<!-- ============================================================
     oe-module-clinical-copilot: Chat Panel
     Injected via RenderEvent::EVENT_BODY_RENDER_POST
     ============================================================ -->
<style>
/* --- Floating toggle button (always visible, bottom-right) --- */
#ai-copilot-toggle {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 9999;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: #0d6efd;
    color: #fff;
    border: none;
    font-size: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
    line-height: 1;
}
#ai-copilot-toggle:hover { background: #0b5ed7; }

/* --- Chat panel container (hidden until toggled) --- */
#ai-copilot-panel {
    position: fixed;
    bottom: 86px;
    right: 24px;
    z-index: 9998;
    width: 380px;
    max-height: 520px;
    /* display:none default; toggled to display:flex by .open class */
    display: none;
    flex-direction: column;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    border-radius: 8px;
    overflow: hidden;
    background: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
}
#ai-copilot-panel.open { display: flex; }

/* --- Header bar --- */
#ai-copilot-header {
    background: #0d6efd;
    color: #fff;
    padding: 10px 14px;
    font-weight: 600;
    font-size: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}
#ai-copilot-header .ai-header-close {
    background: none;
    border: none;
    color: #fff;
    font-size: 18px;
    cursor: pointer;
    line-height: 1;
    padding: 0 2px;
    opacity: 0.85;
}
#ai-copilot-header .ai-header-close:hover { opacity: 1; }

/* --- Message history scroll area --- */
#ai-copilot-messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    background: #f8f9fa;
    min-height: 200px;
    max-height: 360px;
}

/* --- Message bubbles --- */
.ai-msg-user {
    background: #0d6efd;
    color: #fff;
    border-radius: 14px 14px 2px 14px;
    padding: 8px 12px;
    margin: 6px 0 6px auto;
    max-width: 85%;
    width: fit-content;
    word-break: break-word;
}
.ai-msg-assistant {
    background: #fff;
    color: #212529;
    border: 1px solid #dee2e6;
    border-radius: 14px 14px 14px 2px;
    padding: 8px 12px;
    margin: 6px auto 6px 0;
    max-width: 90%;
    width: fit-content;
    word-break: break-word;
    /* preserve newlines from the AI response (bullet points, line breaks) */
    white-space: pre-wrap;
}
.ai-msg-error {
    background: #f8d7da;
    color: #842029;
    border-radius: 8px;
    padding: 8px 12px;
    margin: 6px 0;
    font-size: 12px;
}
/* Citation footnote rendered below an assistant message */
.ai-msg-citations {
    margin-top: 5px;
    font-size: 11px;
    color: #6c757d;
    border-top: 1px solid #eee;
    padding-top: 4px;
}

/* --- Typing indicator spinner --- */
.ai-spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid #dee2e6;
    border-top-color: #0d6efd;
    border-radius: 50%;
    animation: ai-spin 0.7s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
}
@keyframes ai-spin { to { transform: rotate(360deg); } }

/* --- Input area at the bottom --- */
#ai-copilot-input-area {
    display: flex;
    padding: 8px;
    border-top: 1px solid #dee2e6;
    background: #fff;
    gap: 6px;
    flex-shrink: 0;
    align-items: flex-end;
}
#ai-copilot-input {
    flex: 1;
    border: 1px solid #dee2e6;
    border-radius: 18px;
    padding: 7px 13px;
    font-size: 13px;
    outline: none;
    resize: none;
    line-height: 1.4;
    max-height: 80px;
    overflow-y: auto;
    font-family: inherit;
}
#ai-copilot-input:focus { border-color: #0d6efd; box-shadow: 0 0 0 2px rgba(13,110,253,0.15); }
#ai-copilot-submit {
    background: #0d6efd;
    color: #fff;
    border: none;
    border-radius: 18px;
    padding: 7px 14px;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
    font-family: inherit;
    transition: background 0.15s;
}
#ai-copilot-submit:hover:not(:disabled) { background: #0b5ed7; }
#ai-copilot-submit:disabled { background: #adb5bd; cursor: default; }
</style>

<!-- Toggle button — always visible in the corner -->
<button id="ai-copilot-toggle" title="Clinical Co-Pilot" aria-label="Open Clinical Co-Pilot">
    &#128172;
</button>

<!-- Chat panel — hidden by default, shown when toggle is clicked -->
<div id="ai-copilot-panel" role="complementary" aria-label="Clinical Co-Pilot">
    <div id="ai-copilot-header">
        <span>&#129657; Clinical Co-Pilot</span>
        <button class="ai-header-close" id="ai-copilot-close" aria-label="Close" title="Close">&times;</button>
    </div>
    <div id="ai-copilot-messages" aria-live="polite" aria-atomic="false">
        <!-- Welcome message shown on first open -->
        <div class="ai-msg-assistant">Hi! Ask me anything about this patient — recent changes, medications, labs, or upcoming concerns.</div>
    </div>
    <div id="ai-copilot-input-area">
        <textarea
            id="ai-copilot-input"
            rows="1"
            placeholder="Ask about this patient..."
            aria-label="Message"
            maxlength="500"
        ></textarea>
        <button id="ai-copilot-submit" type="button">Send</button>
    </div>
</div>

<script>
(function () {
    'use strict';

    // Ajax URL is set by PHP via json_encode to safely produce a JS string literal.
    var AJAX_URL = <?php echo json_encode($ajaxUrl); ?>;

    var panel     = document.getElementById('ai-copilot-panel');
    var toggle    = document.getElementById('ai-copilot-toggle');
    var closeBtn  = document.getElementById('ai-copilot-close');
    var messages  = document.getElementById('ai-copilot-messages');
    var input     = document.getElementById('ai-copilot-input');
    var submitBtn = document.getElementById('ai-copilot-submit');
    var loading   = false;

    // ---------- Panel open/close ----------
    toggle.addEventListener('click', function () {
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) { input.focus(); }
    });
    closeBtn.addEventListener('click', function () {
        panel.classList.remove('open');
    });

    // ---------- Auto-grow textarea as user types ----------
    input.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    // Enter to submit, Shift+Enter for a newline
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    submitBtn.addEventListener('click', sendMessage);

    // ---------- Append a message bubble ----------
    function appendMessage(text, role, citations, warnings) {
        var div = document.createElement('div');

        if (role === 'error') {
            div.className = 'ai-msg-error';
        } else {
            div.className = role === 'user' ? 'ai-msg-user' : 'ai-msg-assistant';
        }

        div.textContent = text;

        // If the response includes citation objects, render them as a footnote.
        // Citations look like: [{ type: "medication", title: "Metformin 1000mg" }]
        if (citations && citations.length > 0) {
            var citeDiv = document.createElement('div');
            citeDiv.className = 'ai-msg-citations';
            var labels = citations.map(function (c) {
                return (c.title || c.record || c.type || JSON.stringify(c));
            });
            citeDiv.textContent = 'Sources: ' + labels.join(' \u00b7 ');
            div.appendChild(citeDiv);
        }

        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight; // scroll to latest
        return div;
    }

    // ---------- Typing indicator ----------
    function showSpinner() {
        var div = document.createElement('div');
        div.className = 'ai-msg-assistant';
        div.id = 'ai-copilot-spinner';
        div.innerHTML = '<span class="ai-spinner"></span>Thinking\u2026';
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }
    function removeSpinner() {
        var el = document.getElementById('ai-copilot-spinner');
        if (el) { el.remove(); }
    }

    // ---------- Main send function ----------
    function sendMessage() {
        var text = input.value.trim();
        if (!text || loading) { return; }

        // csrf_token_js is a global variable set by OpenEMR's main.php on every page load.
        // It must be included in every POST request — OpenEMR's CsrfUtils rejects requests
        // that don't include a valid token, preventing cross-site request forgery attacks.
        if (typeof csrf_token_js === 'undefined') {
            appendMessage('Session error: CSRF token not available. Please refresh the page.', 'error');
            return;
        }

        // top.getSessionValue('pid') reads the current patient ID from OpenEMR's outer frame.
        // This is the patient currently open in the chart — the same pid that's in the session.
        // We send it as a hint to the server, but the server always uses the session pid as
        // the authoritative source (never trusts client-supplied data).
        var pid = (typeof top.getSessionValue === 'function')
            ? (parseInt(top.getSessionValue('pid'), 10) || 0)
            : 0;

        // Optimistic UI: render the user's message immediately before the server responds
        appendMessage(text, 'user');
        input.value = '';
        input.style.height = 'auto';

        showSpinner();
        loading = true;
        submitBtn.disabled = true;

        // Build the POST body as FormData (multipart/form-data).
        // OpenEMR requires csrf_token_form to be present for all AJAX POST requests.
        var formData = new FormData();
        formData.append('csrf_token_form', csrf_token_js);
        formData.append('pid', pid);
        formData.append('message', text);

        // top.restoreSession() pings OpenEMR to reset the session timeout clock.
        // Without this, a long AI query could time out the session mid-request.
        if (typeof top.restoreSession === 'function') {
            top.restoreSession();
        }

        fetch(AJAX_URL, { method: 'POST', body: formData })
            .then(function (res) {
                // Non-2xx responses may still return JSON with an error field
                if (!res.ok) {
                    return res.json()
                        .then(function (body) { throw new Error(body.error || 'Server error ' + res.status); })
                        .catch(function () { throw new Error('Server error ' + res.status); });
                }
                return res.json();
            })
            .then(function (data) {
                removeSpinner();
                appendMessage(data.answer, 'assistant', data.citations, data.warnings);

                // Surface any verification warnings below the response bubble
                if (data.warnings && data.warnings.length > 0) {
                    var warnDiv = document.createElement('div');
                    warnDiv.className = 'ai-msg-error';
                    warnDiv.style.fontSize = '11px';
                    warnDiv.textContent = '\u26a0\ufe0f ' + data.warnings.join(' \u00b7 ');
                    messages.appendChild(warnDiv);
                    messages.scrollTop = messages.scrollHeight;
                }
            })
            .catch(function (err) {
                removeSpinner();
                appendMessage('Error: ' + err.message, 'error');
            })
            .finally(function () {
                loading = false;
                submitBtn.disabled = false;
                input.focus();
            });
    }

}());
</script>
<!-- end oe-module-clinical-copilot -->
        <?php
    }
}
