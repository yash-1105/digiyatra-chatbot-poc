"""Bind anonymous conversation memory/feedback to a host-only browser capability.

Public conversation IDs identify a conversation inside one anonymous session;
knowing another visitor's conversation/message IDs must not grant its access.
No identifiers or chat content are added to the database schema.
"""
import hashlib
import re
import secrets

from fastapi import Request, Response


def cookie_name(request: Request) -> str:
    return '__Host-dy_chat' if request.app.state.settings.secure_cookies else 'dy_chat'


def conversation_scope(request: Request, conversation_id: str, response: Response | None = None) -> str | None:
    name = cookie_name(request)
    token = request.cookies.get(name)
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        if response is None:
            return None
        token = secrets.token_urlsafe(32)
    if response is not None:
        response.set_cookie(name, token, max_age=86400, path='/', secure=request.app.state.settings.secure_cookies,
                            httponly=True, samesite='strict')
    return hashlib.sha256(f'dy-browser-conversation:v1\0{token}\0{conversation_id}'.encode()).hexdigest()
