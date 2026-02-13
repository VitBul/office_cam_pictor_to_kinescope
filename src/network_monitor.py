"""Network device monitor for CamKinescope.

Scans the local network via ARP to detect extra devices.
When unknown devices are present, upload should be paused
to preserve 4G bandwidth for connected users.
"""

import subprocess
import re
from logger_setup import setup_logger

logger = setup_logger(__name__)

# Regex to parse Windows `arp -a` output lines like:
#   10.0.0.103            00-1a-2b-3c-4d-5e     dynamic
ARP_LINE_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([\w-]+)\s+(\w+)")


def get_arp_devices() -> set:
    """Get set of IP addresses from the ARP table.

    Returns:
        Set of IP address strings visible on the local network.
    """
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, timeout=10,
        )
        ips = set()
        for line in result.stdout.splitlines():
            match = ARP_LINE_RE.search(line)
            if match:
                ip = match.group(1)
                mac_type = match.group(3).lower()
                # Skip broadcast/multicast addresses
                if mac_type == "dynamic" and not ip.endswith(".255"):
                    ips.add(ip)
        return ips
    except Exception as exc:
        logger.warning("ARP scan failed: %s", exc)
        return set()


def ping_subnet(subnet_prefix: str = "10.0.0", start: int = 1, end: int = 254) -> None:
    """Ping sweep to populate ARP table (Windows).

    Runs quick pings with 1 packet, 100ms timeout.
    This ensures ARP table is fresh before checking.
    """
    try:
        # Windows: ping with -n 1 -w 100 (1 packet, 100ms timeout)
        # Run as batch to speed up
        cmd = f'for /L %i in ({start},1,{end}) do @ping -n 1 -w 100 {subnet_prefix}.%i >nul 2>&1'
        subprocess.run(
            ["cmd", "/c", cmd],
            capture_output=True, timeout=120,
        )
    except Exception as exc:
        logger.warning("Ping sweep failed: %s", exc)


def check_extra_devices(config: dict) -> list:
    """Check for unknown devices on the network.

    Args:
        config: Must contain config["network"]["known_devices"] list of IPs.

    Returns:
        List of unknown IP addresses found. Empty list = no extra devices.
    """
    known = set(config.get("network", {}).get("known_devices", []))

    if not known:
        logger.warning("No known_devices configured, skipping network check")
        return []

    # Refresh ARP table with a quick ping sweep
    subnet = config.get("network", {}).get("subnet_prefix", "10.0.0")
    ping_subnet(subnet)

    # Check ARP table
    all_devices = get_arp_devices()
    unknown = [ip for ip in all_devices if ip not in known]

    if unknown:
        logger.info("Extra devices on network: %s", unknown)
    else:
        logger.info("Network clear: only known devices (%d)", len(all_devices & known))

    return unknown


if __name__ == "__main__":
    # Quick test
    print("Scanning ARP table...")
    devices = get_arp_devices()
    print(f"Found {len(devices)} devices:")
    for ip in sorted(devices):
        print(f"  {ip}")
