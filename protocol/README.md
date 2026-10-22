# Protocol experiments

The current Android-to-desktop connection uses newline-delimited JSON over a TLS socket. See [`docs/protocol.md`](../docs/protocol.md) for the implemented session.

The Python validator in this directory describes an experimental signed-message envelope. The live session does not use that envelope yet.
