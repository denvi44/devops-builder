# SPDX-License-Identifier: Apache-2.0
"""Isolation des tests : aucun catalogue personnel ni index rafraîchi du poste ne doit compter."""

from __future__ import annotations

import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="devops-builder-tests-")
os.environ["DEVOPS_BUILDER_HOME"] = _HOME
