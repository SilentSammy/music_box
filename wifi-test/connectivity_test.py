"""Short ESP32-C3 connectivity comparison without stored credentials."""
import network
import socket
import ssl
import time


CONNECT_TIMEOUT_MS = 20_000
STABILITY_SECONDS = 15
TEST_HOST = "example.com"


def http_probe(use_tls):
    port = 443 if use_tls else 80
    address = socket.getaddrinfo(TEST_HOST, port, 0, socket.SOCK_STREAM)[0][-1]
    sock = socket.socket()
    sock.settimeout(10)
    started = time.ticks_ms()
    try:
        sock.connect(address)
        if use_tls:
            if hasattr(ssl, "SSLContext"):
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                sock = context.wrap_socket(sock, server_hostname=TEST_HOST)
            else:
                sock = ssl.wrap_socket(sock, server_hostname=TEST_HOST)

        request = (
            "GET / HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n"
            % TEST_HOST
        )
        sock.write(request.encode())

        received = bytearray()
        while len(received) < 4096:
            chunk = sock.read(512)
            if not chunk:
                break
            received.extend(chunk)

        first_line = bytes(received).split(b"\r\n", 1)[0]
        elapsed = time.ticks_diff(time.ticks_ms(), started)
        return True, elapsed, len(received), first_line
    except Exception as error:
        elapsed = time.ticks_diff(time.ticks_ms(), started)
        return False, elapsed, 0, repr(error)
    finally:
        sock.close()


def test_power(wlan, ssid, password, txpower):
    print("\n=== CONNECTIVITY AT", txpower, "dBm ===")
    wlan.active(False)
    time.sleep_ms(300)
    wlan.active(True)
    wlan.config(txpower=txpower)
    wlan.config(reconnects=2)
    if hasattr(network.WLAN, "PM_NONE"):
        wlan.config(pm=network.WLAN.PM_NONE)
        print("Wi-Fi power management: disabled")
    print("Reported TX power:", wlan.config("txpower"), "dBm")

    target = ssid.encode()
    matches = [entry for entry in wlan.scan() if entry[0] == target]
    if not matches:
        print("Target SSID was not found immediately before connection")
        return {"connected": False, "status": "SSID not found"}
    strongest = max(matches, key=lambda entry: entry[3])
    print(
        "Target found on channel", strongest[2],
        "at", strongest[3], "dBm; security code", strongest[4]
    )

    started = time.ticks_ms()
    wlan.connect(ssid, password, bssid=strongest[1])
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), started) >= CONNECT_TIMEOUT_MS:
            print("Connection failed; status:", wlan.status())
            return {"connected": False, "status": wlan.status()}
        time.sleep_ms(100)

    connect_ms = time.ticks_diff(time.ticks_ms(), started)
    ip, netmask, gateway, dns = wlan.ifconfig()
    print("Connected in", connect_ms, "ms")
    print("IP:", ip, "Gateway:", gateway, "DNS:", dns)

    rssi_values = []
    disconnects = 0
    for second in range(STABILITY_SECONDS):
        if wlan.isconnected():
            rssi = wlan.status("rssi")
            rssi_values.append(rssi)
            print("Second %02d: connected, RSSI %d dBm" % (second + 1, rssi))
        else:
            disconnects += 1
            print("Second %02d: DISCONNECTED, status %s" % (second + 1, wlan.status()))
        time.sleep(1)

    dns_started = time.ticks_ms()
    resolved = socket.getaddrinfo(TEST_HOST, 80)[0][-1][0]
    dns_ms = time.ticks_diff(time.ticks_ms(), dns_started)
    print("DNS:", TEST_HOST, "->", resolved, "in", dns_ms, "ms")

    http_result = http_probe(False)
    https_result = http_probe(True)
    print("HTTP:", http_result)
    print("HTTPS:", https_result)

    return {
        "connected": True,
        "connect_ms": connect_ms,
        "disconnects": disconnects,
        "rssi_min": min(rssi_values) if rssi_values else None,
        "rssi_max": max(rssi_values) if rssi_values else None,
        "rssi_mean": sum(rssi_values) / len(rssi_values) if rssi_values else None,
        "dns_ms": dns_ms,
        "http": http_result[0],
        "https": https_result[0],
    }


def run(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    original_power = 20.0
    results = {}
    try:
        for power in (20.0, 8.5):
            results[power] = test_power(wlan, ssid, password, power)
            wlan.disconnect()
            time.sleep_ms(500)
    finally:
        if not wlan.active():
            wlan.active(True)
        wlan.config(txpower=original_power)
        wlan.disconnect()
        wlan.active(False)
        print("\nRestored 20.0 dBm and disabled Wi-Fi")

    print("\n=== RESULTS ===")
    for power in (20.0, 8.5):
        print(power, "dBm:", results.get(power))
    return results
