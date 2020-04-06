# encoding: utf-8
'''
Created on 2020/04/03

@author: oreyou

'''
from __future__ import unicode_literals, absolute_import, print_function

try:
    string_types = (str, unicode)
    text_type = unicode
    bytes_type = str_type = str
except NameError:
    string_types = (str, )
    text_type = str
    bytes_type = str_type = bytes
def ensure_bytes(it, encoding = "utf-8", errors = "strict"):
    if isinstance(it, text_type):
        return it.encode(encoding, errors)
    elif isinstance(it, bytes_type):
        return it
    else:
        return bytes_type(it)
def ensure_text(it, encoding = "utf-8", errors = "strict"):
    if isinstance(it, bytes_type):
        return it.decode(encoding, errors)
    elif isinstance(it, text_type):
        return it
    else:
        return text_type(it)

LINEEND = "\n"
LINEEND2 = LINEEND * 2
bLINEEND, bLINEEND2 = ensure_bytes(LINEEND), ensure_bytes(LINEEND2)

class Storage(object):
    OPEN_MODE = None
    BUFFERING = 1024 * 1024 * 5
    
    @classmethod
    def sopen(cls, filename, mode, **kwargs):
        kwargs.setdefault("buffering", cls.BUFFERING)
        return open(filename, mode, **kwargs)
    
    @classmethod
    def chunks(cls, fp, size = None):
        size = size or cls.BUFFERING
        while True:
            buf = fp.read(size)
            if not buf:
                break
            yield buf
    
    def __init__(self, stored):
        self.filename = stored
        self.files = []
        self.fp = self.sopen(stored, self.OPEN_MODE)
    
    def __enter__(self):
        return self
    
    def __exit__(self, etype, einst, etrace):
        self.close()
    
    def close(self):
        assert self.fp, OSError("Already closed")
        self.fp.flush()
        self.fp.close()
        self.fp = None
    
class BlobWriter(Storage):
    OPEN_MODE = "wb"
    
    def writebytes(self, filename, abuffer):
        assert not "\n" in filename
        self.files.append((filename, self.fp.tell(), len(abuffer)))
        self.fp.write(abuffer)
    
    def writefile(self, src_filename, filename):
        assert not "\n" in filename
        fp_tell = self.fp.tell()
        opened = isinstance(src_filename, string_types)
        src = self.sopen(src_filename, "rb") if opened else src_filename
        src_begin = src.tell()
        src_len = 0
        for c in self.chunks(src):
            src_len += len(c)
            self.fp.write(c)
        if opened:
            src.close()
        else:
            src.seek(src_begin)
        self.files.append((filename, fp_tell, src_len))
    
    def close(self):
        Storage.close(self)
        with_journal_stored = self.filename + ".tmp"
        with self.sopen(with_journal_stored, "wb", buffering = 1024 * 10) as tmpfp:
            tmpfp.write(
                ensure_bytes(
                    LINEEND.join(
                        ("%s%s%s%s%s" % (fn, LINEEND, fp, LINEEND, fz) for fn, fp, fz in self.files)
                    )
                )
            )
            tmpfp.write(bLINEEND2)
            with self.sopen(self.filename, "rb") as dfp:
                for c in self.chunks(dfp):
                    tmpfp.write(c)
        import os
        os.remove(self.filename)
        os.rename(with_journal_stored, self.filename)

class BlobReader(Storage):
    OPEN_MODE = "rb"
    
    def __init__(self, stored):
        # find CR+CR, and set seekpos
        def _find_crcr_text():
            lines = b""
            with self.sopen(stored, "rb") as fp:
                while True:
                    buf = fp.read(self.BUFFERING)
                    if not buf:
                        print(lines)
                        raise ValueError("Invalid file; No journal parts")
                    lines += buf
                    p = lines.find(bLINEEND2)
                    if p >= 0:
                        lines = lines[:p]
                        break
            offset = len(lines) + len(bLINEEND2)
            lines = ensure_text(lines).split(LINEEND)
            files = dict(
                    zip(
                    lines[::3],
                    zip(
                        map((lambda s: int(s) + offset), lines[1::3]),
                        map((lambda s: int(s)), lines[2::3])
                    )
                )
            )
            return files, offset
        Storage.__init__(self, stored)
        self.files, self._offset = _find_crcr_text()
    
    def read(self, filename):
        found = self.files.get(filename, None)
        if not found:
            raise ValueError("No such entry %s" % filename)
        # TODO: lock?
        fseek, flen = found
        self.fp.seek(fseek)
        return self.fp.read(flen)
        
