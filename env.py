"""
Environment configuration loader.

This module loads environment variables from a `.env` file and exposes them
as Python variables so the rest of the project can access tokens and secrets
safely.
"""

import os
from paths import PROJECT_ROOT

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


def required_int(name: str) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is missing. Please add it to your .env file.")
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer in your .env file.") from None

# DISCORD
DC_TOKEN = os.getenv("DC_TOKEN")


if not DC_TOKEN:
    raise RuntimeError("DC_TOKEN is missing. Please add it to your .env file.")

# NETWORK
PORT = required_int("PORT")
QUERY_PORT = required_int("QUERY_PORT")

# SERVER
NAME=os.getenv("NAME")
PASSWORD = os.getenv("PASSWORD")
APP_ID = os.getenv("APP_ID")

if NAME is None:
    raise RuntimeError("NAME is missing. Please add it to your .env file.")

if PASSWORD is None:
    raise RuntimeError("PASSWORD is missing. Please add it to your .env file.")

if APP_ID is None:
    raise RuntimeError("APP_ID is missing. Please add it to your .env file.")

# RCON
RCON_IP = os.getenv("RCON_IP")
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
RCON_PORT = required_int("RCON_PORT")

if RCON_IP is None:
    raise RuntimeError("RCON_IP is missing. Please add it to your .env file.")

if RCON_PASSWORD is None:
    raise RuntimeError("RCON_PASSWORD is missing. Please add it to your .env file.")
