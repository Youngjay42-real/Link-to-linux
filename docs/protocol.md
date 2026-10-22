# Current session protocol

The live Android-to-desktop connection uses newline-delimited JSON over TLS on TCP port `44888`. Each request is a JSON object with a `kind`; the desktop replies with one JSON object. Pairing and session messages use protocol version `1.0.0`.

The phone verifies the desktop certificate's SHA-256 fingerprint before sending its pairing request. A first pairing request contains `kind`, `protocol_version`, `device_id`, `device_name`, and the six-digit `pairing_code`. An accepted response includes the desktop name and a reconnect token. Later sessions may authenticate with that saved token instead of a new code.

The open session carries status updates and requests for file transfer, photo browsing, notification forwarding, clipboard sync, and media controls. File contents are split into indexed base64 chunks. Transfers are size-limited and use SHA-256 verification.

`protocol/` contains a separate experimental signed-message envelope validator. The live session does not currently use that envelope or its signatures; do not treat those definitions as a description of the active transport.
