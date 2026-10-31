"""The AI layer (D-14). Called only from api/ai.py, so the product works fully with it switched off.

Rules for everything in here: a person approves every change, the model never writes to the database or a
config by itself, and secrets, auth headers and request headers never reach the model (redact.py).
The model is Google Gemini, called over its REST API (client.py).
"""
