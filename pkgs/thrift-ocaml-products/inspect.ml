(* Read the original compiler's typed-source digest without rewriting metadata. *)
let () =
  let metadata = Cmt_format.read_cmt Sys.argv.(1) in
  let source = Option.get metadata.Cmt_format.cmt_sourcefile in
  let digest = Option.get metadata.Cmt_format.cmt_source_digest in
  Printf.printf "%s\t%s\n" source (Digest.to_hex digest)
