# Thin re-export: the real environment lives in disp/core/migrations/env.py so
# every branch shares one implementation (see TECHNICAL-SPEC.md §6).
from disp.core.migrations.env import *  # noqa: F403
