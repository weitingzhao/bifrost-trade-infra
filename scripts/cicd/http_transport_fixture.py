"""Fake only the HTTP transport; urllib's opener and handlers remain real."""
import io
from email.message import Message
from urllib.response import addinfourl


def response(request, code=200, body='{"mirror": false}', headers=None):
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    result = addinfourl(io.BytesIO(body.encode()), message, request.full_url, code)
    result.msg = "fixture"
    return result
