type branch_info = {
  name : string;
  ahead : int;
  behind : int;
  last_commit_date : string;
  last_commit_subject : string;
}

let run_git ~repo_dir args =
  let cmd =
    Printf.sprintf "git -C %s %s"
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
  match status with Unix.WEXITED 0 -> Some output | _ -> None

let count ~repo_dir range =
  match run_git ~repo_dir [ "rev-list"; "--count"; range ] with
  | Some s -> ( try int_of_string s with Failure _ -> 0)
  | None -> 0

let last_commit_meta ~repo_dir ref_ =
  match run_git ~repo_dir [ "log"; "-1"; "--format=%cI\x1f%s"; ref_ ] with
  | Some out -> (
      match String.split_on_char '\x1f' out with
      | [ date; subject ] -> Some (date, subject)
      | date :: rest -> Some (date, String.concat "\x1f" rest)
      | [] -> None)
  | None -> None

let ref_exists ~repo_dir ref_ =
  match run_git ~repo_dir [ "rev-parse"; "--verify"; "--quiet"; ref_ ] with
  | Some s -> String.length s > 0
  | None -> false

let analyze ~repo_dir ~base_ref branches =
  if not (ref_exists ~repo_dir base_ref) then []
  else
    List.filter_map
      (fun name ->
        if (not (ref_exists ~repo_dir name)) || name = base_ref then None
        else
          let ahead = count ~repo_dir (Printf.sprintf "%s..%s" base_ref name) in
          let behind = count ~repo_dir (Printf.sprintf "%s..%s" name base_ref) in
          match last_commit_meta ~repo_dir name with
          | Some (last_commit_date, last_commit_subject) ->
              Some { name; ahead; behind; last_commit_date; last_commit_subject }
          | None -> Some { name; ahead; behind; last_commit_date = ""; last_commit_subject = "" })
      branches
    |> List.sort (fun a b -> compare b.behind a.behind)

let classify (info : branch_info) =
  if info.ahead = 0 then `Merged else if info.behind > 50 then `Likely_stale else `Recent
