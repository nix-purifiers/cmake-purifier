// SPDX-License-Identifier: MIT
use std::io::{self, Write};
use proof_schemas::main::{Envelope, AnswerServiceSyncClient, AnswerServiceSyncHandler, AnswerServiceSyncProcessor, TAnswerServiceSyncClient};
use proof_schemas::value::Value;
use thrift::protocol::{TBinaryInputProtocol, TBinaryOutputProtocol, TSerializable};
use thrift::server::TProcessor;
use thrift::transport::TBufferChannel;
struct Handler;
impl AnswerServiceSyncHandler for Handler {
    fn handle_answer(&self, delta: i32) -> thrift::Result<i32> { Ok(42+delta) }
}
// Let the real generated client flush its native request into the real
// generated processor, then expose that processor's native response bytes.
struct Rpc { request: TBufferChannel, response: TBufferChannel }
impl Write for Rpc {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> { self.request.write(bytes) }
    fn flush(&mut self) -> io::Result<()> {
        self.request.copy_write_buffer_to_read_buffer();
        let mut input=TBinaryInputProtocol::new(self.request.clone(),true);
        let mut output=TBinaryOutputProtocol::new(self.response.clone(),true);
        AnswerServiceSyncProcessor::new(Handler).process(&mut input,&mut output)
            .map_err(|e| io::Error::other(e.to_string()))?;
        self.response.copy_write_buffer_to_read_buffer();
        Ok(())
    }
}
fn main() {
    let mut channel=TBufferChannel::with_capacity(4096,4096);
    let bytes=std::env::args().nth(1).unwrap();
    let wire:Vec<u8>=(0..bytes.len()).step_by(2).map(|i|u8::from_str_radix(&bytes[i..i+2],16).unwrap()).collect();
    assert_eq!(channel.set_readable_bytes(&wire),wire.len());
    let decoded=Envelope::read_from_in_protocol(&mut TBinaryInputProtocol::new(channel.clone(),true)).unwrap();
    assert_eq!(decoded.value.unwrap().answer,Some(42));
    let value=Envelope::new(Value::new(42));
    value.write_to_out_protocol(&mut TBinaryOutputProtocol::new(channel.clone(),true)).unwrap();
    assert_eq!(channel.write_bytes(),wire);
    let request=TBufferChannel::with_capacity(4096,4096);
    let response=TBufferChannel::with_capacity(4096,4096);
    let mut client=AnswerServiceSyncClient::new(TBinaryInputProtocol::new(response.clone(),true),TBinaryOutputProtocol::new(Rpc{request,response},true));
    assert_eq!(client.answer(1).unwrap(),43);
    assert_eq!(proof_schemas::a::Value::new(7).answer,Some(7));
    assert_eq!(proof_schemas::b::Value::new(8).answer,Some(8));
    println!("42:{}:43:7:8",bytes);
}
