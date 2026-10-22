from __future__ import annotations

import argparse

from linktolinux.application import LinkToLinuxApplication
from linktolinux.ui.window import LinkToLinuxWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="Link to Linux desktop client")
    parser.add_argument("--device-name", default="Ubuntu Desktop")
    parser.add_argument("--pair-device", default="")
    parser.add_argument("--pair-code", default="")
    args = parser.parse_args()

    app = LinkToLinuxApplication(device_name=args.device_name)
    if args.pair_device:
        code = args.pair_code or "123456"
        session = app.begin_pairing(args.pair_device, code)
        paired = app.pair_device(args.pair_device, code)
        print({"pairing_session": session, "paired": paired})
        return
    try:
        LinkToLinuxWindow(app).start()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
