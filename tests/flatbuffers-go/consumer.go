// SPDX-License-Identifier: MIT
package main
import (
 "encoding/hex"
 "encoding/json"
 "os"
 "reflect"
 "runtime"
 "unsafe"
 flatbuffers "github.com/google/flatbuffers/go"
 "example.org/schemas/proof"
 "example.org/schemas/a"
 "example.org/schemas/b"
 "example.org/schemas/extra"
)
func check(ok bool) { if !ok { panic("native wire mismatch") } }
func origin(fn interface{}) string { f:=runtime.FuncForPC(reflect.ValueOf(fn).Pointer());file,_:=f.FileLine(f.Entry());return file }
func main() {
 cpp,err:=hex.DecodeString(os.Args[1]);if err!=nil { panic(err) };var value proof.Value
 root:=proof.GetRootAsEnvelope(cpp,0);check(root.Value(&value)!=nil && value.Answer()==42)
 builder:=flatbuffers.NewBuilder(0);proof.ValueStart(builder);proof.ValueAddAnswer(builder,42);v:=proof.ValueEnd(builder);proof.EnvelopeStart(builder);proof.EnvelopeAddValue(builder,v);e:=proof.EnvelopeEnd(builder);builder.FinishWithFileIdentifier(e,[]byte("PRF1"));wire:=builder.FinishedBytes()
 check(proof.GetRootAsEnvelope(wire,0).Value(&value)!=nil && value.Answer()==42)
 other:=flatbuffers.NewBuilder(0);extra.PacketStart(other);extra.PacketAddAnswer(other,44);packet:=extra.PacketEnd(other);other.FinishWithFileIdentifier(packet,[]byte("EXT1"));check(extra.GetRootAsPacket(other.FinishedBytes(),0).Answer()==44)
 first:=flatbuffers.NewBuilder(0);a.ValueStart(first);a.ValueAddAnswer(first,7);av:=a.ValueEnd(first);first.Finish(av);check(a.GetRootAsValue(first.FinishedBytes(),0).Answer()==7)
 second:=flatbuffers.NewBuilder(0);b.ValueStart(second);b.ValueAddAnswer(second,8);bv:=b.ValueEnd(second);second.Finish(bv);check(b.GetRootAsValue(second.FinishedBytes(),0).Answer()==8)
 if err:=os.WriteFile(os.Args[2],wire,0600);err!=nil {panic(err)}
 json.NewEncoder(os.Stdout).Encode(map[string]interface{}{"answer":42,"bits":unsafe.Sizeof(value.Answer())*8,"wire":hex.EncodeToString(wire),"other":44,"qualified":[]int{7,8},"owned":origin(proof.GetRootAsEnvelope),"runtime":origin(flatbuffers.NewBuilder)})
}
