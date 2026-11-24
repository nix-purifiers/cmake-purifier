open Thrift
class memory = object
  inherit Transport.t
  val data = Buffer.create 128
  val mutable position = 0
  val mutable on_flush = (fun () -> ())
  method isOpen = true
  method opn = ()
  method close = ()
  method read output offset length =
    let bytes = Buffer.contents data in
    let count = min length (String.length bytes - position) in
    String.blit bytes position output offset count;
    position <- position + count;
    count
  method write input offset length = Buffer.add_substring data input offset length
  method flush = on_flush ()
  method set_flush callback = on_flush <- callback
  method contents = Buffer.contents data
end
let protocol (transport : memory) = (new TBinaryProtocol.t (transport :> Transport.t) :> Protocol.t)
let () =
  let transport = new memory in
  let value = new Value_types.value in
  value#set_answer 42l;
  let envelope = new Main_types.envelope in
  envelope#set_value value;
  envelope#write (protocol transport);
  let hex = String.concat "" (List.init (String.length transport#contents) (fun i -> Printf.sprintf "%02x" (Char.code transport#contents.[i]))) in
  let expected_field = if Array.length Sys.argv > 1 then int_of_string Sys.argv.(1) else 1 in
  assert (hex = Printf.sprintf "0c%04x0800010000002a0000" expected_field);
  assert ((Main_types.read_envelope (protocol transport))#grab_value#grab_answer = 42l);
  let request, response = new memory, new memory in
  let handler = object
    inherit AnswerService.iface
    method answer delta = Int32.add 42l (Option.get delta)
  end in
  let processor = new AnswerService.processor handler in
  request#set_flush (fun () -> ignore(processor#process (protocol request) (protocol response)));
  let client = new AnswerService.client (protocol response) (protocol request) in
  assert (client#answer 1l = 43l);
  Printf.printf "original OCaml native wire42/RPC43 %s\n" hex
