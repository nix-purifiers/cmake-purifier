#define _GNU_SOURCE
#include <main_types.h>
#include <answer_service.h>
#include <purifier_thrift_c_glib_processor.h>
#include <qa_alpha_types.h>
#include <qb_beta_types.h>
#include <thrift/c_glib/transport/thrift_memory_buffer.h>
#include <thrift/c_glib/protocol/thrift_binary_protocol.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

typedef struct { AnswerServiceHandler parent; } ProofHandler;
typedef struct { AnswerServiceHandlerClass parent; } ProofHandlerClass;
G_DEFINE_TYPE(ProofHandler, proof_handler, TYPE_ANSWER_SERVICE_HANDLER)
static gboolean answer(AnswerServiceIf *self,gint32 *result,const gint32 delta,GError **error){*result=42+delta;return TRUE;}
static gboolean base_answer(BaseServiceIf *self,gint32 *result,const gint32 delta,GError **error){*result=40+delta;return TRUE;}
static void proof_handler_class_init(ProofHandlerClass *klass){((AnswerServiceHandlerClass*)klass)->answer=answer;((BaseServiceHandlerClass*)klass)->base=base_answer;}
static void proof_handler_init(ProofHandler *self){}
PURIFIER_THRIFT_DEFINE_PROCESSOR(ProofProcessor, proof_processor, AnswerServiceProcessor, answer_service_processor_get_type)
PURIFIER_THRIFT_DEFINE_PROCESSOR(ProofBaseProcessor, proof_base_processor, BaseServiceProcessor, base_service_processor_get_type)
static int check_rpc(GType processor_type,gint mode){
 GError *error=NULL;
 ThriftTransport *request=g_object_new(THRIFT_TYPE_MEMORY_BUFFER,NULL),*response=g_object_new(THRIFT_TYPE_MEMORY_BUFFER,NULL);
 ThriftProtocol *input=g_object_new(THRIFT_TYPE_BINARY_PROTOCOL,"transport",request,NULL),*output=g_object_new(THRIFT_TYPE_BINARY_PROTOCOL,"transport",response,NULL);
 AnswerServiceClient *client=g_object_new(TYPE_ANSWER_SERVICE_CLIENT,"input_protocol",output,"output_protocol",input,NULL);
 ProofHandler *handler=g_object_new(proof_handler_get_type(),NULL);
 ThriftProcessor *processor=g_object_new(processor_type,"handler",handler,NULL);
 gint32 result=0;gboolean sent=mode==1?answer_service_client_send_answer(ANSWER_SERVICE_IF(client),1,&error):base_service_client_send_base(BASE_SERVICE_IF(client),2,&error);if(!sent||error)return 5;
 if(!thrift_processor_process(processor,input,output,&error)||error)return 6;
 gboolean received=mode==1?answer_service_client_recv_answer(ANSWER_SERVICE_IF(client),&result,&error):base_service_client_recv_base(BASE_SERVICE_IF(client),&result,&error);
 if(mode==1){
   if(!received||result!=43||error){fprintf(stderr,"RPC recv=%d result=%d error=%s\n",received,result,error?error->message:"none");return 7;}
   if(!base_service_client_send_base(BASE_SERVICE_IF(client),2,&error)||error)return 10;
   if(!thrift_processor_process(processor,input,output,&error)||error)return 11;
   if(!base_service_client_recv_base(BASE_SERVICE_IF(client),&result,&error)||error||result!=42)return 12;
 }else if(mode==2){
   if(!received||error||result!=42)return 14;
 }else{
   if(received||!error||!strstr(error->message,"Invalid method name: 'base'"))return 13;
   g_clear_error(&error);
 }

 g_object_unref(processor);g_object_unref(handler);g_object_unref(client);g_object_unref(input);g_object_unref(output);g_object_unref(request);g_object_unref(response);return 0;
}
int main(void){
 GError *error=NULL;
 Value *value=g_object_new(TYPE_VALUE,"answer",42,NULL);
 Envelope *envelope=g_object_new(TYPE_ENVELOPE,"value",value,NULL);
 ThriftTransport *memory=g_object_new(THRIFT_TYPE_MEMORY_BUFFER,NULL);
 ThriftProtocol *protocol=g_object_new(THRIFT_TYPE_BINARY_PROTOCOL,"transport",memory,NULL);
 gint32 size=thrift_struct_write(THRIFT_STRUCT(envelope),protocol,&error);if(size<=0||error)return 1;
 guint8 *bytes=g_malloc(size);if(thrift_transport_read(memory,bytes,size,&error)!=size||error)return 2;
 printf("42:");for(int i=0;i<size;++i)printf("%02x",bytes[i]);puts("");
 if(!thrift_transport_write(memory,bytes,size,&error)||error)return 3;
 Envelope *restored=g_object_new(TYPE_ENVELOPE,NULL);if(thrift_struct_read(THRIFT_STRUCT(restored),protocol,&error)!=size||restored->value->answer!=42||error)return 4;
 int rpc_result=check_rpc(TYPE_BASE_SERVICE_PROCESSOR,0);if(rpc_result)return 20+rpc_result;
 rpc_result=check_rpc(proof_processor_get_type(),1);if(rpc_result)return 40+rpc_result;
 rpc_result=check_rpc(proof_base_processor_get_type(),2);if(rpc_result)return 60+rpc_result;
 rpc_result=check_rpc(TYPE_BASE_SERVICE_PROCESSOR,0);if(rpc_result)return 80+rpc_result;
 Dl_info owned={0},runtime={0};if(!dladdr((void*)value_get_type,&owned)||!dladdr((void*)thrift_struct_write,&runtime))return 8;
 gpointer a=g_object_new(qa_value_get_type(),NULL),b=g_object_new(qb_value_get_type(),NULL);gint av=0,bv=0;g_object_get(a,"answer",&av,NULL);g_object_get(b,"answer",&bv,NULL);if(av!=7||bv!=8)return 9;
 printf("43\n%s\n%s\n7 8\nraw-native-invalid-method\ninherited-rpc42\n",owned.dli_fname,runtime.dli_fname);
 g_free(bytes);g_object_unref(a);g_object_unref(b);g_object_unref(restored);g_object_unref(protocol);g_object_unref(memory);g_object_unref(envelope);g_object_unref(value);
 return 0;
}
