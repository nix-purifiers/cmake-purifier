# SPDX-License-Identifier: MIT
import sys,json
from cffi import FFI
ffi=FFI();ffi.cdef('''
size_t value_get_type(void); size_t envelope_get_type(void);
size_t qa_value_get_type(void); size_t qb_value_get_type(void);
size_t thrift_memory_buffer_get_type(void); size_t thrift_binary_protocol_get_type(void);
void *g_object_new(size_t,const char*,...); void g_object_get(void*,const char*,...); void g_object_unref(void*);
int thrift_struct_write(void*,void*,void**); int thrift_struct_read(void*,void*,void**);
int thrift_transport_read(void*,void*,unsigned int,void**); int thrift_transport_write(void*,const void*,unsigned int,void**);
''');lib=ffi.dlopen(sys.argv[1]);wire=bytes.fromhex(sys.argv[2]);error=ffi.new('void**')
value=lib.g_object_new(lib.value_get_type(),b'answer',ffi.cast('int',42),ffi.NULL)
envelope=lib.g_object_new(lib.envelope_get_type(),b'value',value,ffi.NULL)
transport=lib.g_object_new(lib.thrift_memory_buffer_get_type(),ffi.NULL)
protocol=lib.g_object_new(lib.thrift_binary_protocol_get_type(),b'transport',transport,ffi.NULL)
assert lib.thrift_struct_write(envelope,protocol,error)==len(wire) and error[0]==ffi.NULL
buffer=ffi.new('unsigned char[]',len(wire));assert lib.thrift_transport_read(transport,buffer,len(wire),error)==len(wire) and bytes(ffi.buffer(buffer,len(wire)))==wire and error[0]==ffi.NULL
assert lib.thrift_transport_write(transport,buffer,len(wire),error) and error[0]==ffi.NULL
restored=lib.g_object_new(lib.envelope_get_type(),ffi.NULL);assert lib.thrift_struct_read(restored,protocol,error)==len(wire) and error[0]==ffi.NULL
child=ffi.new('void**');lib.g_object_get(restored,b'value',child,ffi.NULL);answer=ffi.new('int*');lib.g_object_get(child[0],b'answer',answer,ffi.NULL);assert answer[0]==42
for get_type,expected in [(lib.qa_value_get_type,7),(lib.qb_value_get_type,8)]:
    obj=lib.g_object_new(get_type(),ffi.NULL);actual=ffi.new('int*');lib.g_object_get(obj,b'answer',actual,ffi.NULL);assert actual[0]==expected;lib.g_object_unref(obj)
for obj in [child[0],restored,protocol,transport,envelope,value]:lib.g_object_unref(obj)
print(json.dumps({'answer':answer[0],'wire':bytes(ffi.buffer(buffer,len(wire))).hex(),'qualified':[7,8]}))
