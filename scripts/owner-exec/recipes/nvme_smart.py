"""Read-only NVMe health read for ubt-k3s-05, standard library only.
Sends exactly two NVMe admin commands to the controller character device /dev/nvme0: Identify Controller (0x06)
and Get Log Page 0x02 (SMART / Health). Never opens a namespace block device, never sends any other opcode,
never writes, formats, trims or benchmarks. Reads PCIe link speed and width from sysfs. Prints parsed fields;
the serial number is NOT printed (the duty check asked for no sn)."""
import ctypes
import fcntl
import os
import struct

DEV = "/dev/nvme0"
SYS = "/sys/class/nvme/nvme0"
IOCTL_ADMIN_CMD = 0xC0484E41       # NVME_IOCTL_ADMIN_CMD = _IOWR('N', 0x41, struct nvme_admin_cmd /72 bytes/)
ALLOWED_OPCODES = {0x06, 0x02}     # Identify, Get Log Page. Nothing else may ever be sent.
CMD_FMT = "<BBHIIIQQIIIIIIIIII"     # opcode flags rsvd nsid cdw2 cdw3 meta addr meta_len data_len cdw10..15 timeout result = 72 bytes
assert struct.calcsize(CMD_FMT) == 72


def admin(fd, opcode, nsid, cdw10, length):
    if opcode not in ALLOWED_OPCODES:
        raise SystemExit("refused: opcode %#x is not allowed" % opcode)
    buf = ctypes.create_string_buffer(length)
    cmd = bytearray(struct.pack(CMD_FMT, opcode, 0, 0, nsid, 0, 0, 0, ctypes.addressof(buf), 0, length,
                                cdw10, 0, 0, 0, 0, 0, 5000, 0))
    fcntl.ioctl(fd, IOCTL_ADMIN_CMD, cmd)
    return bytes(buf)


def text(b):
    return b.decode("ascii", "replace").strip()


def u(b, off, n):
    return int.from_bytes(b[off:off + n], "little")


def parse_identify(b):
    return {
        "model": text(b[24:64]), "firmware": text(b[64:72]),
        "nvme_version": "%d.%d.%d" % (u(b, 80, 4) >> 16, (u(b, 80, 4) >> 8) & 0xFF, u(b, 80, 4) & 0xFF),
        "warning_temp_c": u(b, 266, 2) - 273, "critical_temp_c": u(b, 268, 2) - 273,
        "volatile_write_cache": bool(b[525] & 1),
    }


def parse_smart(b):
    sensors = [u(b, 200 + 2 * i, 2) - 273 for i in range(8) if u(b, 200 + 2 * i, 2)]
    written = u(b, 48, 16)
    return {
        "critical_warning": "0x%02x" % b[0], "temperature_c": u(b, 1, 2) - 273,
        "available_spare_pct": b[3], "available_spare_threshold_pct": b[4], "percentage_used": b[5],
        "data_units_written": written, "data_written_gb": round(written * 512000 / 1e9),
        "data_units_read": u(b, 32, 16), "power_cycles": u(b, 112, 16), "power_on_hours": u(b, 128, 16),
        "unsafe_shutdowns": u(b, 144, 16), "media_errors": u(b, 160, 16), "num_err_log_entries": u(b, 176, 16),
        "warning_temp_time_min": u(b, 192, 4), "critical_temp_time_min": u(b, 196, 4), "temp_sensors_c": sensors,
    }


def sysfs(name):
    try:
        with open(os.path.join(SYS, "device", name)) as f:
            return f.read().strip()
    except OSError as e:
        return "unreadable: %s" % e.strerror


def main():
    fd = os.open(DEV, os.O_RDONLY)          # the controller node, read-only; never nvme0n1
    try:
        ident = parse_identify(admin(fd, 0x06, 0, 1, 4096))                     # CNS=1: Identify Controller
        smart = parse_smart(admin(fd, 0x02, 0xFFFFFFFF, (127 << 16) | 0x02, 512))  # LID=2, 128 dwords
    finally:
        os.close(fd)
    link = {k: sysfs(k) for k in ("current_link_speed", "current_link_width", "max_link_speed", "max_link_width")}
    for title, d in (("identify", ident), ("smart", smart), ("pcie", link)):
        print("== " + title)
        for k, v in d.items():
            print("%s=%s" % (k, v))
    ok = bool(ident["model"]) and -20 < smart["temperature_c"] < 120   # an all-zero reply (command refused) shows as no model and -273 C
    print("RESULT=PASS" if ok else "RESULT=FAIL reason=reply looks empty (the controller may have refused the command)")


if __name__ == "__main__":
    main()
