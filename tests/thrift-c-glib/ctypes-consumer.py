# SPDX-License-Identifier: MIT
import ctypes as c,json,sys
from pathlib import Path
library=Path(sys.argv[1])
lib=c.CDLL(str(library))
for name in ['value_get_type','envelope_get_type','thrift_memory_buffer_get_type','thrift_binary_protocol_get_type','qa_value_get_type','qb_value_get_type']:
 f=getattr(lib,name);f.argtypes=[];f.restype=c.c_size_t
lib.g_object_new.argtypes=[c.c_size_t,c.c_char_p];lib.g_object_new.restype=c.c_void_p
lib.g_object_get.argtypes=[c.c_void_p,c.c_char_p];lib.g_object_get.restype=None
lib.g_object_unref.argtypes=[c.c_void_p];lib.g_object_unref.restype=None
for name in ['thrift_struct_write','thrift_struct_read']:
 f=getattr(lib,name);f.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p];f.restype=c.c_int32
lib.thrift_transport_read.argtypes=[c.c_void_p,c.c_void_p,c.c_uint32,c.c_void_p];lib.thrift_transport_read.restype=c.c_int32
lib.thrift_transport_write.argtypes=[c.c_void_p,c.c_void_p,c.c_uint32,c.c_void_p];lib.thrift_transport_write.restype=c.c_int
value=lib.g_object_new(lib.value_get_type(),b'answer',c.c_int(42),c.c_void_p())
envelope=lib.g_object_new(lib.envelope_get_type(),b'value',c.c_void_p(value),c.c_void_p())
transport=lib.g_object_new(lib.thrift_memory_buffer_get_type(),None)
protocol=lib.g_object_new(lib.thrift_binary_protocol_get_type(),b'transport',c.c_void_p(transport),c.c_void_p())
wire=bytes.fromhex(sys.argv[2])
error=c.c_void_p();count=lib.thrift_struct_write(envelope,protocol,c.byref(error));assert count==len(wire) and not error.value,(count,error.value)
bytes_=c.create_string_buffer(len(wire));assert lib.thrift_transport_read(transport,bytes_,len(wire),c.byref(error))==len(wire) and not error.value;assert bytes_.raw==wire
assert lib.thrift_transport_write(transport,c.c_char_p(wire),len(wire),c.byref(error)) and not error.value
restored=lib.g_object_new(lib.envelope_get_type(),None);assert lib.thrift_struct_read(restored,protocol,c.byref(error))==len(wire) and not error.value
child=c.c_void_p();lib.g_object_get(restored,b'value',c.byref(child),c.c_void_p());answer=c.c_int();lib.g_object_get(child,b'answer',c.byref(answer),c.c_void_p());assert answer.value==42
for name,expected in [('qa_value_get_type',7),('qb_value_get_type',8)]:
 obj=lib.g_object_new(getattr(lib,name)(),None);actual=c.c_int();lib.g_object_get(obj,b'answer',c.byref(actual),c.c_void_p());assert actual.value==expected;lib.g_object_unref(obj)
for obj in [child,restored,protocol,transport,envelope,value]:lib.g_object_unref(obj)
result={'library':str(library),'answer':answer.value,'wire':bytes_.raw.hex(),'nativeCppWire':wire.hex(),'api':'generated get_type, GLib GObject constructors/properties, native Thrift struct/transport API; no private struct layouts'}
print(json.dumps(result))
