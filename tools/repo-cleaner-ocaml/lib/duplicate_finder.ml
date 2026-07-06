type group = {
  hash : string;
  size_bytes : int;
  files : Scanner.file_entry list;
}

module StringMap = Map.Make (String)

let find (entries : Scanner.file_entry list) : group list =
  let non_empty = List.filter (fun (e : Scanner.file_entry) -> e.size_bytes > 0) entries in
  let by_hash =
    List.fold_left
      (fun acc (e : Scanner.file_entry) ->
        match Hasher.file_hash e.abs_path with
        | h -> StringMap.update h (function None -> Some [ e ] | Some xs -> Some (e :: xs)) acc
        | exception Sys_error _ -> acc)
      StringMap.empty non_empty
  in
  let groups =
    StringMap.fold
      (fun hash files acc ->
        match files with
        | [] | [ _ ] -> acc
        | (first : Scanner.file_entry) :: _ :: _ ->
            { hash; size_bytes = first.size_bytes; files } :: acc)
      by_hash []
  in
  List.sort
    (fun a b ->
      let waste g = g.size_bytes * (List.length g.files - 1) in
      compare (waste b) (waste a))
    groups
