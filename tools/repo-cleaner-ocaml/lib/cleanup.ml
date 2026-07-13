type action = {
  keep : Scanner.file_entry;
  remove : Scanner.file_entry list;
}

let repo_label (e : Scanner.file_entry) =
  match String.index_opt e.rel_path '/' with
  | Some i -> String.sub e.rel_path 0 i
  | None -> e.rel_path

let same_repo (g : Duplicate_finder.group) =
  match g.files with
  | [] -> true
  | first :: rest ->
      let label = repo_label first in
      List.for_all (fun f -> repo_label f = label) rest

let default_protected_name_fragments = [ "latest"; "current"; "stable" ]

let has_protected_name ~protected_name_fragments (g : Duplicate_finder.group) =
  List.exists
    (fun (f : Scanner.file_entry) ->
      let lower = String.lowercase_ascii (Filename.basename f.rel_path) in
      List.exists
        (fun frag ->
          let fl = String.length lower and pl = String.length frag in
          let rec go i = i + pl <= fl && (String.sub lower i pl = frag || go (i + 1)) in
          go 0)
        protected_name_fragments)
    g.files

let plan ?(protected_name_fragments = default_protected_name_fragments) (groups : Duplicate_finder.group list) :
    action list =
  groups
  |> List.filter same_repo
  |> List.filter (fun g -> not (has_protected_name ~protected_name_fragments g))
  |> List.map (fun (g : Duplicate_finder.group) ->
         match List.sort (fun (a : Scanner.file_entry) b -> compare a.rel_path b.rel_path) g.files with
         | keep :: remove -> { keep; remove }
         | [] -> assert false (* Duplicate_finder groups always have 2+ files *))

let apply ~dry_run (actions : action list) : (Scanner.file_entry * exn option) list =
  if dry_run then []
  else
    List.concat_map
      (fun a ->
        List.map
          (fun (f : Scanner.file_entry) ->
            match Sys.remove f.abs_path with
            | () -> (f, None)
            | exception e -> (f, Some e))
          a.remove)
      actions
