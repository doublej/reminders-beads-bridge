"""Type a message into a live Ghostty tab via macOS GUI automation.

macOS gives no silent path: TIOCSTI is root-only and writing to the tty only
paints the display. So we drive the GUI — activate Ghostty, match the target
tab by its (glyph-stripped) title in the tab bar, click it, paste, press Return.

Hard guards keep this safe even untested: every failure path raises before any
keystroke, and we re-verify the focused tab title *after* switching, so a wrong
or unreachable tab aborts instead of typing into the wrong session. Requires
Accessibility permission for the process running the daemon, and the target tab
must be on the active Space (cross-Space windows are invisible to AX).
"""

import subprocess

# Tab/window titles are "<status-glyph><space><title>"; drop the 2-char prefix.
_SCRIPT = """
on stripPrefix(t)
    if (length of t) > 2 then return text 3 thru -1 of t
    return t
end stripPrefix

on run argv
    set target to item 1 of argv
    tell application "Ghostty" to activate
    delay 0.25
    tell application "System Events"
        if not (exists process "ghostty") then return "ERR:ghostty-not-running"
        tell process "ghostty"
            if (count of windows) is 0 then return "ERR:no-window-on-space"
            repeat with w in windows
                set matched to false
                try
                    set tg to first UI element of w whose role is "AXTabGroup"
                    repeat with rb in (radio buttons of tg)
                        if my stripPrefix(title of rb) is target then
                            perform action "AXPress" of rb
                            set matched to true
                            exit repeat
                        end if
                    end repeat
                end try
                if not matched and (my stripPrefix(title of w)) is target then
                    perform action "AXRaise" of w
                    set matched to true
                end if
                if matched then
                    delay 0.2
                    set ft to ""
                    try
                        set ft to my stripPrefix(title of (value of attribute "AXFocusedWindow"))
                    end try
                    if ft is not target then return "ERR:focus-mismatch:" & ft
                    keystroke "v" using {command down}
                    delay 0.1
                    key code 36
                    return "OK"
                end if
            end repeat
            return "ERR:tab-not-found"
        end tell
    end tell
end run
"""


class InjectError(RuntimeError):
    pass


def accessibility_ok() -> bool:
    """True if this process may drive System Events (Accessibility granted)."""
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return name of first process'],
        capture_output=True, text=True, timeout=10,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def _clip_get() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


def _clip_set(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True)


def type_into_tab(title: str, text: str) -> None:
    """Paste `text` + Return into the Ghostty tab titled `title`.

    Raises InjectError (before any keystroke) if the tab can't be reached or
    the focused tab doesn't match — the caller keeps the message for retry.
    """
    if not title:
        raise InjectError("tab has no title to match")
    saved = _clip_get()
    _clip_set(text)
    try:
        result = subprocess.run(
            ["osascript", "-", title], input=_SCRIPT,
            capture_output=True, text=True, timeout=20,
        )
    finally:
        _clip_set(saved)
    out = (result.stdout or result.stderr).strip()
    if out != "OK":
        raise InjectError(out or "osascript failed")
