"""Compare ESP32-C3 Wi-Fi scans at default and reduced TX power."""
import network
import time


LOW_POWER_DBM = 8.5
REFERENCE_POWER_DBM = 20.0
SCANS_PER_POWER = 3
PAUSE_BETWEEN_SCANS_MS = 1000


def readable_ssid(raw_ssid):
    if not raw_ssid:
        return "<hidden>"
    try:
        return raw_ssid.decode("utf-8")
    except UnicodeError:
        return repr(raw_ssid)


def scan_at_power(wlan, label, requested_power):
    wlan.config(txpower=requested_power)
    actual_power = wlan.config("txpower")
    print("\n===", label, "===")
    print("Requested TX power:", requested_power, "dBm")
    print("Reported TX power:", actual_power, "dBm")

    counts = []
    observations = {}
    for scan_number in range(1, SCANS_PER_POWER + 1):
        networks = wlan.scan()
        counts.append(len(networks))
        print("\nScan", scan_number, "found", len(networks), "access points")

        for ssid, bssid, channel, rssi, security, hidden in sorted(
            networks, key=lambda item: item[3], reverse=True
        ):
            name = readable_ssid(ssid)
            print("  %4d dBm  ch %2d  %s" % (rssi, channel, name))
            if bssid not in observations:
                observations[bssid] = [name, []]
            observations[bssid][1].append(rssi)

        if scan_number < SCANS_PER_POWER:
            time.sleep_ms(PAUSE_BETWEEN_SCANS_MS)

    stable = 0
    for name, readings in observations.values():
        if len(readings) == SCANS_PER_POWER:
            stable += 1

    result = {
        "requested": requested_power,
        "actual": actual_power,
        "counts": counts,
        "unique": len(observations),
        "stable": stable,
    }
    print("\nSummary for", label)
    print("  Counts:", counts)
    print("  Mean count:", sum(counts) / len(counts))
    print("  Unique access points:", result["unique"])
    print("  Seen in every scan:", stable)
    return result


def main():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    default_power = wlan.config("txpower")
    print("Wi-Fi interface active")
    print("TX power on entry:", default_power, "dBm")

    try:
        default_result = scan_at_power(
            wlan, "REFERENCE POWER", REFERENCE_POWER_DBM
        )
        reduced_result = scan_at_power(wlan, "REDUCED POWER", LOW_POWER_DBM)

        print("\n=== COMPARISON ===")
        print("Reference mean AP count:", sum(default_result["counts"]) / SCANS_PER_POWER)
        print("Reduced mean AP count:", sum(reduced_result["counts"]) / SCANS_PER_POWER)
        print("Reference stable APs:", default_result["stable"])
        print("Reduced stable APs:", reduced_result["stable"])
    finally:
        wlan.config(txpower=default_power)
        wlan.active(False)
        print("Restored TX power and disabled Wi-Fi")


if __name__ == "__main__":
    main()
