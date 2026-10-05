"""Optional framework integration and non-blocking connectivity diagnostics."""
import time
from app_info import VERSION


def installed_version():
    try:
        import platform_services
        return platform_services.installation_context().get("current_version") or VERSION
    except (ImportError, AttributeError, OSError, ValueError):
        return VERSION


def wifi_network():
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return "Offline"
        for key in ("ssid", "essid"):
            try:
                name = wlan.config(key)
                return name.decode() if isinstance(name, bytes) else str(name)
            except (OSError, ValueError):
                pass
        return "Connected"
    except (ImportError, OSError):
        return "Unavailable"


class WifiProbe:
    def __init__(self):
        self.started = time.ticks_ms()
        self.result = "Connecting"
        self.owns_connection = False
        self.wlan = None
        try:
            import network
            self.wlan = network.WLAN(network.STA_IF)
            if self.wlan.isconnected():
                self.result = "OK"
                return
            try:
                import platform_services
            except ImportError:
                from wifi_secrets import SSID, PASSWORD
                self.owns_connection = True
                self.wlan.active(True)
                self.wlan.config(txpower=8.5, reconnects=2)
                self.wlan.connect(SSID, PASSWORD)
            else:
                # Do not take ownership of the updater's radio or credentials.
                platform_services.start_wifi_setup()
        except ImportError:
            self.result = "No credentials"
        except (OSError, ValueError, AttributeError) as error:
            self.result = "Error"
            print("Wi-Fi test:", repr(error))

    def update(self, now):
        if self.result != "Connecting":
            return
        if self.wlan.isconnected():
            self.result = "OK"
            print("Wi-Fi hardware test connected:", self.wlan.ifconfig()[0])
        elif time.ticks_diff(now, self.started) >= 45000:
            self.result = "Failed/offline"

    def close(self):
        if self.owns_connection and self.wlan is not None:
            self.wlan.disconnect()
            self.wlan.active(False)
