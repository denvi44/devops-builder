# SPDX-License-Identifier: Apache-2.0
"""Point d'entrée des exécutables (PyInstaller) : même comportement que la commande devops-builder."""

import sys

from devops_builder.cli import main

if __name__ == "__main__":
    sys.exit(main())
