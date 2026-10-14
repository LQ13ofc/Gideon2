#!/usr/bin/env python3
"""Fixture namespace probe; outputs booleans only, never environment values."""
import json,os
print(json.dumps({'secret_present':'GIDEON_AUDIT_SECRET' in os.environ,'private_home':os.environ.get('HOME')=='/tmp'}))
