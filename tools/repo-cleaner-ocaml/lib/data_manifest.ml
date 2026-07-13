let default_extensions = [ ".parquet"; ".db"; ".db.gz"; ".gz"; ".csv"; ".json"; ".xlsx" ]

let ends_with ~suffix s =
  let sl = String.length suffix and l = String.length s in
  l >= sl && String.sub s (l - sl) sl = suffix

let starts_with ~prefix s =
  let pl = String.length prefix and l = String.length s in
  l >= pl && String.sub s 0 pl = prefix

let is_data_file ?(extensions = default_extensions) (e : Scanner.file_entry) =
  let lower = String.lowercase_ascii e.rel_path in
  List.exists (fun ext -> ends_with ~suffix:ext lower) extensions

let lfs_header = "version https://git-lfs.github.com/spec/v1"

let parse_lfs_pointer contents =
  if not (starts_with ~prefix:lfs_header contents) then None
  else
    let lines = String.split_on_char '\n' contents in
    let oid =
      List.find_map
        (fun line ->
          if starts_with ~prefix:"oid sha256:" line then
            Some (String.trim (String.sub line 11 (String.length line - 11)))
          else None)
        lines
    in
    let size =
      List.find_map
        (fun line ->
          if starts_with ~prefix:"size " line then
            match int_of_string_opt (String.trim (String.sub line 5 (String.length line - 5))) with
            | Some n -> Some n
            | None -> None
          else None)
        lines
    in
    match (oid, size) with Some o, Some s -> Some (o, s) | _ -> None

type cataloged = {
  file : Scanner.file_entry;
  true_size_bytes : int;
  is_lfs_pointer : bool;
  content_key : string option;
}

(* A real LFS pointer file is always small (a handful of short text lines);
   reading a bounded prefix is enough to recognize one without loading a
   multi-megabyte real parquet/db file into memory just to reject it. *)
let probe_bytes = 1024

let read_prefix path n =
  let ic = open_in_bin path in
  Fun.protect
    ~finally:(fun () -> close_in_noerr ic)
    (fun () ->
      let len = min n (in_channel_length ic) in
      really_input_string ic len)

let catalog ?(extensions = default_extensions) (entries : Scanner.file_entry list) : cataloged list =
  entries
  |> List.filter (is_data_file ~extensions)
  |> List.map (fun (e : Scanner.file_entry) ->
         match read_prefix e.abs_path probe_bytes with
         | prefix -> (
             match parse_lfs_pointer prefix with
             | Some (oid, size) ->
                 { file = e; true_size_bytes = size; is_lfs_pointer = true; content_key = Some ("lfs:" ^ oid) }
             | None -> (
                 match Hasher.file_hash e.abs_path with
                 | h -> { file = e; true_size_bytes = e.size_bytes; is_lfs_pointer = false; content_key = Some ("raw:" ^ h) }
                 | exception Sys_error _ ->
                     { file = e; true_size_bytes = e.size_bytes; is_lfs_pointer = false; content_key = None }))
         | exception Sys_error _ ->
             { file = e; true_size_bytes = e.size_bytes; is_lfs_pointer = false; content_key = None })

module StringMap = Map.Make (String)

let duplicates (catalogued : cataloged list) : Duplicate_finder.group list =
  (* Restricted to LFS pointers on purpose: a non-pointer data file (real
     bytes already on disk) hashes identically whether Duplicate_finder or
     this function does the hashing, so including it here would just
     re-report a finding {!Duplicate_finder.find} already made over ALL
     files, data or not. The only comparison this function adds that
     Duplicate_finder can't already make just as well is "these two LFS
     pointers name the same oid" -- which is also literally what
     Duplicate_finder would conclude by hashing the pointer text itself,
     but restricting to pointers here keeps this function's purpose (and
     its report section) honestly about LFS-tracked data, not a second
     copy of the general duplicate scan. *)
  let lfs_only = List.filter (fun c -> c.is_lfs_pointer) catalogued in
  let by_relpath =
    List.fold_left (fun acc c -> StringMap.add c.file.Scanner.rel_path c acc) StringMap.empty lfs_only
  in
  let entries = List.map (fun c -> c.file) lfs_only in
  Duplicate_finder.group_by_key
    ~key_of:(fun (e : Scanner.file_entry) ->
      match StringMap.find_opt e.rel_path by_relpath with Some c -> c.content_key | None -> None)
    ~size_of:(fun (e : Scanner.file_entry) ->
      match StringMap.find_opt e.rel_path by_relpath with Some c -> c.true_size_bytes | None -> e.size_bytes)
    entries

let kind_of rel_path =
  let lower = String.lowercase_ascii rel_path in
  match List.find_opt (fun ext -> ends_with ~suffix:ext lower) default_extensions with
  | Some ext -> ext
  | None -> ""

let to_csv_rows (catalogued : cataloged list) : string list list =
  [ "path"; "kind"; "true_size_bytes"; "is_lfs_pointer"; "content_key" ]
  :: List.map
       (fun c ->
         [
           c.file.Scanner.rel_path;
           kind_of c.file.Scanner.rel_path;
           string_of_int c.true_size_bytes;
           string_of_bool c.is_lfs_pointer;
           (match c.content_key with Some k -> k | None -> "");
         ])
       catalogued
