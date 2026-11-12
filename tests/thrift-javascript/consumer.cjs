const assert=require('node:assert/strict');
const thrift=require('thrift');
const schemas=require('@proof/thrift-schemas');
const {Envelope}=schemas.schema;
const {Value}=schemas.common;
const service=schemas.rpc;
assert.equal(new schemas.a.Value({answer:7}).answer,7);
assert.equal(new schemas.b.Value({answer:8}).answer,8);
async function main(){
 const wire=Buffer.from(process.argv[2],'hex');
 let restored;
 thrift.TBufferedTransport.receiver(transport=>{restored=new Envelope();restored[Symbol.for('read')](new thrift.TBinaryProtocol(transport));})(wire);
 assert.equal(restored.value.answer,42);
 let bytes;
 const transport=new thrift.TBufferedTransport(undefined,data=>{bytes=data;});
 new Envelope({value:new Value({answer:42})})[Symbol.for('write')](new thrift.TBinaryProtocol(transport));transport.flush();assert.deepEqual(bytes,wire);
 const socket=process.argv[3];
 const options={transport:thrift.TBufferedTransport,protocol:thrift.TBinaryProtocol};
 const server=thrift.createServer(service,{answer(delta){return 42+delta;}},options);
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(socket,resolve);});
 const connection=thrift.createUDSConnection(socket,options);
 await new Promise((resolve,reject)=>{connection.once('error',reject);connection.once('connect',resolve);});
 const client=thrift.createClient(service,connection);
 try {assert.equal(await client.answer(1),43);} finally {connection.end();await new Promise(resolve=>server.close(resolve));}
 console.log(JSON.stringify({answer:42,wire:bytes.toString('hex'),rpc:43,schema:require.resolve('@proof/thrift-schemas/schema'),runtime:require.resolve('thrift')}));
}
main().catch(e=>{console.error(e);process.exit(1);});
