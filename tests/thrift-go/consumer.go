// SPDX-License-Identifier: MIT
package main
import (
 "context"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "os"
 "reflect"
 "runtime"
 sdk "github.com/apache/thrift/lib/go/thrift"
 schemas "example.org/schemas/main_value"
 value "example.org/schemas/common_value"
)
type handler struct{}
func (handler) Answer(_ context.Context, delta int32) (int32,error) { return 42+delta,nil }
type requestTransport struct { *sdk.TMemoryBuffer; processor sdk.TProcessor; response *sdk.TMemoryBuffer }
func (t *requestTransport) Flush(ctx context.Context) error { _,err:=t.processor.Process(ctx,sdk.NewTBinaryProtocolTransport(t.TMemoryBuffer),sdk.NewTBinaryProtocolTransport(t.response));return err }
func origin(fn any) string { f:=runtime.FuncForPC(reflect.ValueOf(fn).Pointer());path,_:=f.FileLine(f.Entry());return path }
func main() {
 ctx:=context.Background();buffer:=sdk.NewTMemoryBuffer();original:=&schemas.Envelope{Value:&value.Value{Answer:42}}
 if err:=original.Write(ctx,sdk.NewTBinaryProtocolTransport(buffer));err!=nil { panic(err) }
 wire:=append([]byte(nil),buffer.Bytes()...);decoded:=schemas.NewEnvelope()
 if err:=decoded.Read(ctx,sdk.NewTBinaryProtocolTransport(buffer));err!=nil || decoded.Value.Answer!=42 {panic("roundtrip")}
 response:=sdk.NewTMemoryBuffer();request:=&requestTransport{TMemoryBuffer:sdk.NewTMemoryBuffer(),processor:schemas.NewAnswerServiceProcessor(handler{}),response:response}
 client:=schemas.NewAnswerServiceClientProtocol(request,sdk.NewTBinaryProtocolTransport(response),sdk.NewTBinaryProtocolTransport(request));answer,err:=client.Answer(ctx,1)
 if err!=nil || answer!=43 {panic(fmt.Sprint("rpc ",answer," ",err))}
 result:=map[string]any{"answer":42,"rpc":answer,"wire":hex.EncodeToString(wire),"owned":origin(schemas.NewEnvelope),"runtime":origin(sdk.NewTMemoryBuffer)}
 if err:=json.NewEncoder(os.Stdout).Encode(result);err!=nil {panic(err)}
}
