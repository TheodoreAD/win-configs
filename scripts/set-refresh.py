"""List or set the primary display's refresh rate at its current resolution.

Only rates the driver offers at the current resolution are accepted. A change is saved to the
registry, so it survives a reboot. Standard library only (ctypes over user32).

Usage, from the repo root:
  uv run --no-project python scripts/set-refresh.py        # list available rates
  uv run --no-project python scripts/set-refresh.py 165    # switch to 165 Hz
"""

import ctypes
import sys
from ctypes import wintypes

ENUM_CURRENT_SETTINGS = -1
DM_DISPLAYFREQUENCY = 0x400000
CDS_UPDATEREGISTRY = 0x1
DISP_CHANGE = {0: "OK", 1: "RESTART needed", -1: "FAILED", -2: "BADMODE", -3: "NOTUPDATED", -5: "BADPARAM"}


class DEVMODEW(ctypes.Structure):
    _fields_ = [  # noqa: RUF012 -- ctypes reads this; its members are typed Any by design
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", wintypes.LONG),
        ("dmPositionY", wintypes.LONG),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


user32 = ctypes.windll.user32


def new_mode() -> DEVMODEW:
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    return dm


def main() -> int:
    cur = new_mode()
    user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(cur))
    w, h = int(cur.dmPelsWidth), int(cur.dmPelsHeight)
    rates: set[int] = set()
    i = 0
    dm = new_mode()
    while user32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
        if (int(dm.dmPelsWidth), int(dm.dmPelsHeight)) == (w, h):
            rates.add(int(dm.dmDisplayFrequency))
        i += 1
    print(f"current: {w}x{h} @ {cur.dmDisplayFrequency} Hz; available at {w}x{h}: {sorted(rates)}")
    if len(sys.argv) < 2:
        return 0
    hz = int(sys.argv[1])
    if hz not in rates:
        print(f"{hz} Hz is not offered at {w}x{h}")
        return 1
    cur.dmDisplayFrequency = hz
    cur.dmFields = DM_DISPLAYFREQUENCY
    rc = user32.ChangeDisplaySettingsExW(None, ctypes.byref(cur), None, CDS_UPDATEREGISTRY, None)
    print(f"set {hz} Hz: {DISP_CHANGE.get(rc, rc)}")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
