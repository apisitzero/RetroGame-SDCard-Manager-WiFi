# -*- coding: utf-8 -*-
"""
License & MAC Address Manager for RetroGame & SD Card Manager Version WiFi v1.1
Crafted for: เพจเล่าเรื่องเกม (Lao Reuang Game) & BallModThaiGame
Zero-dependency Python 3 standard library
"""

import os
import sys
import json
import base64
import hmac
import hashlib
from datetime import datetime, date
import uuid
import re

# Internal HMAC secret key for signing licenses (Admin Key)
_LICENSE_SECRET = b"BallModThaiGame_LaoReuangGame_SecretKey_2026_ArkOS"

def get_device_mac():
    """
    Detect the physical hardware MAC address of the device (Wi-Fi dongle or Ethernet).
    Checks Linux sysfs first (ArkOS wlan0 / ra0 / eth0), then standard fallback.
    """
    net_path = "/sys/class/net"
    if os.path.exists(net_path):
        # Prioritize wireless interfaces (wlan0, wlan1, ra0, etc.)
        for iface in sorted(os.listdir(net_path)):
            if iface.startswith("wlan") or iface.startswith("ra") or iface.startswith("wl"):
                addr_file = os.path.join(net_path, iface, "address")
                if os.path.exists(addr_file):
                    try:
                        with open(addr_file, "r") as f:
                            mac = f.read().strip().upper()
                            if mac and len(mac) == 17 and mac != "00:00:00:00:00:00":
                                return mac
                    except Exception:
                        pass

        # Then check any non-loopback interface
        for iface in os.listdir(net_path):
            if iface == "lo":
                continue
            addr_file = os.path.join(net_path, iface, "address")
            if os.path.exists(addr_file):
                try:
                    with open(addr_file, "r") as f:
                        mac = f.read().strip().upper()
                        if mac and len(mac) == 17 and mac != "00:00:00:00:00:00":
                            return mac
                except Exception:
                    pass

    # Fallback using uuid
    try:
        node = uuid.getnode()
        mac = ':'.join(re.findall('..', '%012X' % node)).upper()
        return mac
    except Exception:
        return "00:00:00:00:00:00"

def generate_signed_license(mac: str, expires_at: str, customer_name: str = "Member") -> str:
    """
    Admin tool: Generates a signed base64 license token tied to a specific MAC and expiry date.
    expires_at format: YYYY-MM-DD
    """
    payload = {
        "mac": mac.strip().upper(),
        "expires_at": expires_at.strip(),
        "customer": customer_name.strip(),
        "tier": "premium"
    }
    raw_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    b64_payload = base64.urlsafe_b64encode(raw_json).decode('ascii')
    sig = hmac.new(_LICENSE_SECRET, raw_json, hashlib.sha256).hexdigest()[:16]
    return f"{b64_payload}.{sig}"

def decode_and_verify_token(token_str: str) -> dict:
    """Decodes and cryptographically verifies a license token."""
    if not token_str or "." not in token_str:
        return None
    try:
        b64_part, sig_part = token_str.strip().split(".", 1)
        raw_json = base64.urlsafe_b64decode(b64_part.encode('ascii'))
        expected_sig = hmac.new(_LICENSE_SECRET, raw_json, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig_part, expected_sig):
            return None
        return json.loads(raw_json.decode('utf-8'))
    except Exception:
        return None

class LicenseManager:
    def __init__(self, app_dir: str = None):
        self.app_dir = app_dir or os.path.dirname(os.path.abspath(__file__))
        self.device_mac = get_device_mac()
        self.license_info = self._check_license()

    def _check_license(self) -> dict:
        """
        Validates the license against the physical device MAC and current system date.
        License can be supplied via environment variable (from .sh) or license.key file.
        """
        token = os.environ.get("RETROGAME_LICENSE") or os.environ.get("PREMIUM_LICENSE")
        
        if not token:
            key_file = os.path.join(self.app_dir, "license.key")
            if os.path.exists(key_file):
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        token = f.read().strip()
                except Exception:
                    pass

        default_free = {
            "tier": "free",
            "is_premium": False,
            "device_mac": self.device_mac,
            "days_left": 0,
            "expires_at": None,
            "customer": "Free User",
            "status_text": "Free Tier",
            "reason": "no_license"
        }

        if not token:
            return default_free

        payload = decode_and_verify_token(token)
        if not payload:
            default_free["reason"] = "invalid_signature"
            return default_free

        licensed_mac = payload.get("mac", "").strip().upper()
        expires_str = payload.get("expires_at", "").strip()
        customer = payload.get("customer", "Valued Member")

        # 1. Verify MAC Address match
        if licensed_mac != self.device_mac:
            default_free["reason"] = "mac_mismatch"
            return default_free

        # 2. Verify Expiry Date
        try:
            exp_date = datetime.strptime(expires_str, "%Y-%m-%d").date()
            today = date.today()
            days_left = (exp_date - today).days

            if days_left < 0:
                default_free["reason"] = "expired"
                default_free["expires_at"] = expires_str
                default_free["customer"] = customer
                return default_free

            # Passed all checks -> Valid Premium!
            return {
                "tier": "premium",
                "is_premium": True,
                "device_mac": self.device_mac,
                "days_left": days_left,
                "expires_at": expires_str,
                "customer": customer,
                "status_text": f"Premium ({days_left} days left)",
                "reason": "valid"
            }
        except Exception as e:
            default_free["reason"] = f"date_parse_error: {e}"
            return default_free

    def is_premium(self) -> bool:
        return self.license_info.get("is_premium", False)

    def get_license_data(self) -> dict:
        return self.license_info

if __name__ == "__main__":
    mgr = LicenseManager()
    print("Detected MAC:", mgr.device_mac)
    print("License Status:", mgr.get_license_data())

    # Demo generate license for 30 days
    from datetime import timedelta
    test_exp = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    sample_token = generate_signed_license(mgr.device_mac, test_exp, "Somchai Tester")
    print("\nSample Signed Token for this machine:")
    print(sample_token)

    # Test verification
    verified = decode_and_verify_token(sample_token)
    print("Verified Payload:", verified)
