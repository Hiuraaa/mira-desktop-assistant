"""Small, read-only Windows status snapshot, fetched only after session consent."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from ctypes import wintypes
from pathlib import Path


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


class MEMORY_STATUS(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def battery_status() -> str:
    if sys.platform != "win32":
        raise RuntimeError("Trạng thái pin hiện chỉ hỗ trợ Mira trên Windows.")
    power = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
        raise RuntimeError("Windows chưa cung cấp trạng thái pin lúc này.")
    if power.BatteryFlag == 255:
        return "Windows chưa xác định được trạng thái pin. " + (
            "Máy đang cắm nguồn." if power.ACLineStatus == 1 else "Chưa xác định được nguồn điện.")
    if power.BatteryFlag & 128:
        return "Máy tính không báo có pin (có thể là máy bàn). " + (
            "Đang dùng nguồn điện." if power.ACLineStatus == 1 else "Không xác định nguồn điện.")
    level = f"{power.BatteryLifePercent}%" if power.BatteryLifePercent <= 100 else "không rõ"
    charging = ("Đang sạc pin, có cắm nguồn." if power.BatteryFlag & 8 else
                "Đang cắm nguồn; Windows không báo pin đang được sạc." if power.ACLineStatus == 1 else
                "Đang dùng pin, chưa cắm nguồn." if power.ACLineStatus == 0 else
                "Chưa xác định được có cắm sạc hay không.")
    return f"Pin laptop: {level}. {charging}"


def device_status() -> str:
    """No network, shell, file enumeration or background monitoring."""
    result = [battery_status()]
    memory = MEMORY_STATUS()
    memory.dwLength = ctypes.sizeof(memory)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        gib = 1024 ** 3
        result.append(f"RAM còn trống: {memory.ullAvailPhys / gib:.1f}/{memory.ullTotalPhys / gib:.1f} GiB.")
    try:
        usage = shutil.disk_usage(Path.home().anchor)
        result.append(f"Ổ hệ thống còn trống: {usage.free / (1024 ** 3):.1f} GiB.")
    except OSError:
        pass
    result.append("Số luồng xử lý: " + str(os.cpu_count() or "không rõ") + ".")
    return " ".join(result)
