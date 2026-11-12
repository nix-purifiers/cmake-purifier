// SPDX-License-Identifier: MIT
use proof_schemas::proof as envelope;
use proof_schemas::proof as value;
fn main() {
 let args:Vec<String>=std::env::args().collect();let cpp:Vec<u8>=(0..args[1].len()).step_by(2).map(|i|u8::from_str_radix(&args[1][i..i+2],16).unwrap()).collect();
 let decoded=envelope::root_as_envelope(&cpp).unwrap();assert_eq!(decoded.value().unwrap().answer(),42);assert!(envelope::envelope_buffer_has_identifier(&cpp));
 assert_eq!(std::mem::size_of_val(&decoded.value().unwrap().answer())*8,args[3].parse::<usize>().unwrap());
 let mut builder=flatbuffers::FlatBufferBuilder::new();let v=value::Value::create(&mut builder,&value::ValueArgs{answer:42});let root=envelope::Envelope::create(&mut builder,&envelope::EnvelopeArgs{value:Some(v)});envelope::finish_envelope_buffer(&mut builder,root);
 for (which,n) in [(0,7),(1,8)] { let mut q=flatbuffers::FlatBufferBuilder::new(); if which==0 { let off=proof_schemas::a::Value::create(&mut q,&proof_schemas::a::ValueArgs{answer:n});q.finish(off,None);assert_eq!(flatbuffers::root::<proof_schemas::a::Value>(q.finished_data()).unwrap().answer(),n); } else { let off=proof_schemas::b::Value::create(&mut q,&proof_schemas::b::ValueArgs{answer:n});q.finish(off,None);assert_eq!(flatbuffers::root::<proof_schemas::b::Value>(q.finished_data()).unwrap().answer(),n); } }
 let mut other=flatbuffers::FlatBufferBuilder::new();let packet=proof_schemas::extra::Packet::create(&mut other,&proof_schemas::extra::PacketArgs{answer:44});proof_schemas::extra::finish_packet_buffer(&mut other,packet);assert_eq!(proof_schemas::extra::root_as_packet(other.finished_data()).unwrap().answer(),44);assert!(proof_schemas::extra::packet_buffer_has_identifier(other.finished_data()));
 let bytes=builder.finished_data();assert_eq!(envelope::root_as_envelope(bytes).unwrap().value().unwrap().answer(),42);std::fs::write(&args[2],bytes).unwrap();println!("42:{}:{}",args[3],bytes.iter().map(|b|format!("{:02x}",b)).collect::<String>());
}
