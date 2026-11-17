"""
Environment configuration loader.

This module loads environment variables from a `.env` file and exposes them
as Python variables so the rest of the project can access tokens and secrets
safely.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# DISCORD
DC_TOKEN = os.getenv("DC_TOKEN")


if DC_TOKEN is None:
    raise RuntimeError("DC_TOKEN is missing. Please add it to your .env file.")

# NETWORK
PORT = int(os.getenv("PORT"))
QUERY_PORT = int(os.getenv("QUERY_PORT"))

if PORT is None:
    raise RuntimeError("PORT is missing. Please add it to your .env file.")

if QUERY_PORT is None:
    raise RuntimeError("QUERY_PORT is missing. Please add it to your .env file.")

# SERVER
NAME=os.getenv("NAME")
PASSWORD = os.getenv("PASSWORD")
APP_ID = os.getenv("APP_ID")
SERVER_EXE_PATH = os.getenv("SERVER_EXE_PATH")
SERVER_PATH = os.getenv("SERVER_PATH")
CLUSTER_DIR = os.getenv("CLUSTER_DIR")
STEAMCMD_PATH = os.getenv("STEAMCMD_PATH")
LOG_DIR = os.getenv("LOG_DIR")

if NAME is None:
    raise RuntimeError("NAME is missing. Please add it to your .env file.")

if PASSWORD is None:
    raise RuntimeError("PASSWORD is missing. Please add it to your .env file.")

if APP_ID is None:
    raise RuntimeError("APP_ID is missing. Please add it to your .env file.")

if SERVER_PATH is None:
    raise RuntimeError("SERVER_PATH is missing. Please add it to your .env file.")

if SERVER_EXE_PATH is None:
    raise RuntimeError("SERVER_EXE_PATH is missing. Please add it to your .env file.")

if CLUSTER_DIR is None:
    raise RuntimeError("CLUSTER_DIR is missing. Please add it to your .env file.")

if STEAMCMD_PATH is None:
    raise RuntimeError("STEAMCMD_PATH is missing. Please add it to your .env file.")

if LOG_DIR is None:
    raise RuntimeError("LOG_DIR is missing. Please add it to your .env file.")

# RCON
RCON_IP = os.getenv("RCON_IP")
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
RCON_PORT = int(os.getenv("RCON_PORT"))

if RCON_IP is None:
    raise RuntimeError("RCON_IP is missing. Please add it to your .env file.")

if RCON_PASSWORD is None:
    raise RuntimeError("HF_TOKEN is missing. Please add it to your .env file.")

if RCON_PORT is None:
    raise RuntimeError("HF_TOKEN is missing. Please add it to your .env file.")
