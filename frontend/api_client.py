import requests
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

def get(path: str, params: dict = None):
    resp = requests.get(f"{BACKEND_URL}{path}", params=params)
    resp.raise_for_status()
    return resp.json()

def post(path: str, json: dict = None):
    resp = requests.post(f"{BACKEND_URL}{path}", json=json)
    resp.raise_for_status()
    return resp.json()

def put(path: str, json: dict = None):
    resp = requests.put(f"{BACKEND_URL}{path}", json=json)
    resp.raise_for_status()
    return resp.json()
