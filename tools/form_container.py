"""Replace an ordinary form module, preserving every other container payload."""
import re
import struct


def read_entries(data):
    def block(offset):
        chunks, total = [], None
        while offset != 0x7fffffff:
            header = data[offset:offset + 31]
            if not re.fullmatch(rb'\r\n[0-9a-fA-F]{8} [0-9a-fA-F]{8} [0-9a-fA-F]{8} \r\n', header):
                raise ValueError('Invalid container block')
            size, page, following = [int(v, 16) for v in header.split()]
            total = size if total is None else total
            count = min(page, total - sum(map(len, chunks)))
            chunks.append(data[offset + 31:offset + 31 + count])
            offset = following
        return b''.join(chunks)
    return [(block(h), block(b)) for h, b, end in struct.iter_unpack('<III', block(16))]


def replace_module(data, module):
    entries = read_entries(data)
    chunks = []
    toc = []
    offset = 16 + 31 + 512
    def packed(payload):
        return ('\r\n%08x %08x 7fffffff \r\n' % (len(payload), len(payload))).encode('ascii') + payload
    for header, body in entries:
        if header[20:].decode('utf-16-le').rstrip('\0') == 'module':
            body = b'\xef\xbb\xbf' + module.replace('\n', '\r\n').encode('utf-8')
        hb, bb = packed(header), packed(body)
        toc.append(struct.pack('<III', offset, offset + len(hb), 0x7fffffff))
        chunks.extend([hb, bb])
        offset += len(hb) + len(bb)
    directory = b''.join(toc)
    root = ('\r\n%08x 00000200 7fffffff \r\n' % len(directory)).encode('ascii')
    output = data[:16] + root + directory.ljust(512, b'\0') + b''.join(chunks)
    assert [(h, b) for h, b in read_entries(output) if h[20:].decode('utf-16-le').rstrip('\0') != 'module'] == [(h, b) for h, b in entries if h[20:].decode('utf-16-le').rstrip('\0') != 'module']
    return output
