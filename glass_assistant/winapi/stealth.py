"""
stealth.py
==========
Windows-only window tricks, done with raw Win32 API calls via `ctypes`
(no extra dependency needed).

Two features:

1. hide_from_capture(hwnd)
   Uses SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE.
   The window stays visible on your real screen, but shows up BLANK in
   any software screen-share or recording (Zoom / Meet / Teams / OBS).

2. set_click_through(hwnd, enabled)
   Adds the WS_EX_LAYERED + WS_EX_TRANSPARENT styles so mouse clicks
   pass straight through the glass panel to whatever app is behind it.

`hwnd` is the native window handle. With PyQt you get it from
`int(widget.winId())`.

NOTE: WDA_EXCLUDEFROMCAPTURE blocks SOFTWARE capture only. It cannot
hide your screen from a separate physical camera pointed at the monitor.
"""

import ctypes
from ctypes import wintypes

# --- Win32 constants ----------------------------------------------------
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011   # Windows 10 2004+ / Windows 11

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

user32 = ctypes.windll.user32

# Tell ctypes the argument/return types so 64-bit handles work correctly.
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_void_p

user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p


def hide_from_capture(hwnd: int, enabled: bool = True) -> bool:
    """Make the window invisible to software screen capture."""
    affinity = WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE
    return bool(user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), affinity))


def set_click_through(hwnd: int, enabled: bool = True) -> None:
    """Let mouse clicks pass through the window to apps behind it."""
    style = user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT  # keep LAYERED for transparency
    user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
