type group = {
  hash : string;
  size_bytes : int;
  files : Scanner.file_entry list;
}

module StringMap = Map.Make (String)

let group_by_key ~key_of ~size_of (entries : Scanner.file_entry list) : group list =
  let by_key =
    List.fold_left
      (fun acc (e : Scanner.file_entry) ->
        match key_of e with
        | Some k -> StringMap.update k (function None -> Some [ e ] | Some xs -> Some (e :: xs)) acc
        | None -> acc)
      StringMap.empty entries
  in
  let groups =
    StringMap.fold
      (fun hash files acc ->
        match files with
        | [] | [ _ ] -> acc
        | (first : Scanner.file_entry) :: _ :: _ ->
            { hash; size_bytes = size_of first; files } :: acc)
      by_key []
  in
  List.sort
    (fun a b ->
      let waste g = g.size_bytes * (List.length g.files - 1) in
      compare (waste b) (waste a))
    groups

let find (entries : Scanner.file_entry list) : group list =
  let non_empty = List.filter (fun (e : Scanner.file_entry) -> e.size_bytes > 0) entries in
  group_by_key
    ~key_of:(fun (e : Scanner.file_entry) ->
      match Hasher.file_hash e.abs_path with h -> Some h | exception Sys_error _ -> None)
    ~size_of:(fun (e : Scanner.file_entry) -> e.size_bytes)
    non_empty
