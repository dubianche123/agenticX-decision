#!/usr/bin/env python3
"""Configure a user-supplied OpenAI-compatible endpoint locally."""
import getpass
import json
from urllib.parse import urlsplit

import mzt_common


def main() -> None:
    base_url = input("OpenAI-compatible base URL (https://host/v1): ").strip()
    url = urlsplit(base_url)
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise SystemExit("Use an HTTP(S) endpoint without embedded credentials or query parameters.")
    model = input("Model ID: ").strip()
    key = getpass.getpass("API key (hidden): ").strip()
    if not model or not key:
        raise SystemExit("Model ID and key are required.")
    mzt_common.write_private(mzt_common.config_path(".mzt_demo_key"), key)
    mzt_common.write_private(mzt_common.config_path(".mzt_demo_profile.json"),
                             json.dumps({"base_url": base_url, "model": model}, indent=2))
    print("Saved local settings with mode 600. Credentials are never printed.")


if __name__ == "__main__":
    main()
