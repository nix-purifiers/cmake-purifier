/* SPDX-License-Identifier: MIT */
#ifndef PURIFIER_THRIFT_C_GLIB_PROCESSOR_H
#define PURIFIER_THRIFT_C_GLIB_PROCESSOR_H
#include <thrift/c_glib/processor/thrift_dispatch_processor.h>

/* Some native generators declare a service-specific dispatch_call slot without
 * overriding ThriftDispatchProcessor's inherited virtual method. Bridge those
 * public class slots through ordinary GObject subclassing. The caller supplies
 * the actual generated instance/class names and get_type function; no private
 * offsets, replacement processor, protocol, or generated source edits are used.
 * Include the native generated service header before invoking this macro.
 */
#define PURIFIER_THRIFT_DEFINE_PROCESSOR(TypeName, type_name, NativeType, native_get_type) \
  typedef struct { NativeType parent; } TypeName; \
  typedef struct { NativeType##Class parent; } TypeName##Class; \
  G_DEFINE_TYPE(TypeName, type_name, native_get_type()) \
  static void type_name##_class_init(TypeName##Class *klass) { \
    NativeType##Class *native_class = g_type_class_peek_parent(klass); \
    THRIFT_DISPATCH_PROCESSOR_CLASS(klass)->dispatch_call = native_class->dispatch_call; \
  } \
  static void type_name##_init(TypeName *self) { (void)self; }
#endif
