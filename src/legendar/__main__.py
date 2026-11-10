"""Permite abrir a aplicação com ``python -m legendar``."""

from __future__ import annotations

import sys

from legendar.bootstrap import main

if __name__ == "__main__":
    sys.exit(main())
