type info = {
  last_commit_date : string;
  last_commit_subject : string;
}

let run_git ~repo_dir args =
  let cmd =
    Printf.sprintf "git -C %s %s 2>/dev/null"
      (Filename.quote repo_dir)
      (String.concat " " (List.map Filename.quote args))
  in
  let ic = Unix.open_process_in cmd in
  let buf = Buffer.create 256 in
  (try
     while true do
       Buffer.add_channel buf ic 1
     done
   with End_of_file -> ());
  let status = Unix.close_process_in ic in
  let output = String.trim (Buffer.contents buf) in
  match status with Unix.WEXITED 0 when output <> "" -> Some output | _ -> None

let lookup ~repo_dir ~rel_path_in_repo =
  match run_git ~repo_dir [ "log"; "-1"; "--format=%cI\x1f%s"; "--"; rel_path_in_repo ] with
  | Some out -> (
      match String.split_on_char '\x1f' out with
      | date :: rest when rest <> [] -> Some { last_commit_date = date; last_commit_subject = String.concat "\x1f" rest }
      | _ -> None)
  | None -> None

let most_recent (entries : (Scanner.file_entry * info option) list) =
  entries
  |> List.filter_map (fun (f, i) -> match i with Some i -> Some (f, i) | None -> None)
  |> List.sort (fun (_, a) (_, b) -> compare b.last_commit_date a.last_commit_date)
  |> function (f, _) :: _ -> Some f | [] -> None
