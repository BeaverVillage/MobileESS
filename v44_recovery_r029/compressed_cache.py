"""Lossless payload compression; exact input identities and independent outputs."""
import zlib
from time import perf_counter


def pack(raw):
    if len(raw)<32768:return b'\0'+raw
    encoded=zlib.compress(raw,1)
    return b'\1'+encoded if len(encoded)<len(raw)*.9 else b'\0'+raw


def unpack(payload):
    if payload[:1]==b'\0':return payload[1:]
    if payload[:1]==b'\1':return zlib.decompress(payload[1:])
    raise ValueError('R029_CACHE_PAYLOAD_TAG')
