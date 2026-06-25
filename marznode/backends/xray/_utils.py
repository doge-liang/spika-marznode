"""xray utilities"""

import re
import subprocess
from typing import Dict


def get_version(xray_path: str) -> str | None:
    """
    get xray version by running its executable
    :param xray_path:
    :return: xray version
    """
    cmd = [xray_path, "version"]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
    match = re.match(r"^Xray (\d+\.\d+\.\d+)", output)
    if match:
        return match.group(1)
    return None


def get_x25519(xray_path: str, private_key: str = None) -> Dict[str, str] | None:
    """
    get x25519 public key using the private key
    :param xray_path:
    :param private_key:
    :return: x25519 publickey
    """
    cmd = [xray_path, "x25519"]
    if private_key:
        cmd.extend(["-i", private_key])
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8")
    private_match = re.search(
        r"^(?:Private key|PrivateKey):\s*(.+)$",
        output,
        re.MULTILINE,
    )
    public_match = re.search(
        r"^(?:Public key|Password \(PublicKey\)):\s*(.+)$",
        output,
        re.MULTILINE,
    )
    if private_match and public_match:
        return {
            "private_key": private_match.group(1).strip(),
            "public_key": public_match.group(1).strip(),
        }
    return None
