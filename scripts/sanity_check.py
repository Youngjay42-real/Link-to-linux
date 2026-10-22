#!/usr/bin/env python3

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    root / 'desktop' / 'pyproject.toml',
    root / 'android' / 'settings.gradle.kts',
    root / 'README.md',
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    print('Missing required files:')
    for item in missing:
        print(f'  - {item}')
    sys.exit(1)
print('sanity-check: ok')
