"""Redaction applied to anything that may leave the machine.

Masks phone numbers (MSISDN), IPv4 addresses and email addresses.
Message IDs are kept: they are opaque and needed for tracing.
"""

from __future__ import annotations

import re

MSISDN_RE = re.compile(r"(?<!\d)(?:\+?62|0)8\d{7,11}(?!\d)")
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def mask_msisdn(num: str) -> str:
    digits = num.lstrip("+")
    if len(digits) <= 7:
        return "*" * len(digits)
    return digits[:5] + "*" * (len(digits) - 8) + digits[-3:]


def redact(text: str) -> str:
    text = MSISDN_RE.sub(lambda m: mask_msisdn(m.group(0)), text)
    text = IPV4_RE.sub("<ip>", text)
    text = EMAIL_RE.sub("<email>", text)
    return text
