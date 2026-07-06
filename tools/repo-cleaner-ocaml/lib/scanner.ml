type file_entry = {
  abs_path : string;
  rel_path : string;
  size_bytes : int;
}

let strip_root_prefix ~root path =
  let root_len = String.length root in
  if String.length path > root_len && String.sub path 0 root_len = root then
    let rest = String.sub path root_len (String.length path - root_len) in
    if String.length rest > 0 && rest.[0] = '/' then
      String.sub rest 1 (String.length rest - 1)
    else rest
  else path

let scan ?(exclude_dirs = [ ".git" ]) root =
  let results = ref [] in
  let rec walk dir =
    let entries =
      try Sys.readdir dir with Sys_error _ -> [||]
    in
    Array.sort compare entries;
    Array.iter
      (fun name ->
        let path = Filename.concat dir name in
        (* Sys.is_directory follows symlinks; we check is_symlink first so a
           symlink (to a directory or otherwise) is never traversed into --
           the only way a walk over a real filesystem can loop forever. *)
        let is_symlink =
          match Unix.lstat path with
          | { Unix.st_kind = Unix.S_LNK; _ } -> true
          | _ -> false
          | exception Unix.Unix_error _ -> false
        in
        if is_symlink then ()
        else if Sys.is_directory path then (
          if not (List.mem name exclude_dirs) then walk path)
        else
          match Unix.stat path with
          | { Unix.st_size; _ } ->
              results :=
                {
                  abs_path = path;
                  rel_path = strip_root_prefix ~root path;
                  size_bytes = st_size;
                }
                :: !results
          | exception Unix.Unix_error _ -> ())
      entries
  in
  walk root;
  List.rev !results
