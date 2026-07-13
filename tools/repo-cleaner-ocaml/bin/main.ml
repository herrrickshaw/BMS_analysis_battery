open Repo_cleaner_lib

let roots = ref []
let repo_dir = ref None
let base_ref = ref "main"
let branches = ref []
let out_path = ref None
let data_manifest_out = ref None
let apply = ref false

let spec =
  [
    ( "--root",
      Arg.String (fun s -> roots := s :: !roots),
      "<dir>  Directory to scan for duplicate/near-duplicate files. Repeatable -- \
       pass one --root per repo checkout to analyze across all of them at once." );
    ( "--repo-dir",
      Arg.String (fun s -> repo_dir := Some s),
      "<dir>  A git repo checkout to run branch-staleness analysis against (optional)." );
    ("--base-ref", Arg.String (fun s -> base_ref := s), "<ref>  Base ref for branch comparison (default: main).");
    ( "--branch",
      Arg.String (fun s -> branches := s :: !branches),
      "<name>  Branch to include in staleness analysis. Repeatable." );
    ("--out", Arg.String (fun s -> out_path := Some s), "<path>  Write the report here instead of stdout.");
    ( "--data-manifest-out",
      Arg.String (fun s -> data_manifest_out := Some s),
      "<path>  Write a CSV catalog of every data file (parquet/db/csv/json/xlsx/gz) \
       found under all --root directories, with true size and content key parsed \
       from Git LFS pointers where applicable -- no real LFS bytes downloaded." );
    ( "--apply",
      Arg.Set apply,
      "  Actually delete redundant copies -- but ONLY within-repo exact duplicates \
       (every copy shares the same --root). Cross-repo duplicates, name clusters, and \
       branches are never touched by --apply; those always need a human decision. \
       Default: print the plan, delete nothing." );
  ]

let usage =
  "repo_cleaner --root <dir> [--root <dir> ...] [--repo-dir <dir> --branch <name> ...] \
   [--out report.md] [--data-manifest-out data.csv]\n\n\
   Structural redundancy report only: exact-duplicate files, data-source duplicates \
   (via LFS pointer oid, without downloading real LFS content), name-based doc-sprawl \
   clusters, and branch staleness vs a base ref. Never deletes anything -- every \
   finding is a candidate for a human to review."

let () =
  Arg.parse spec (fun _ -> ()) usage;
  if !roots = [] then (
    prerr_endline "At least one --root is required.\n";
    prerr_endline usage;
    exit 1);

  (* When scanning several repos in one run, a bare rel_path like
     "full_japan_market_scan.py" is ambiguous -- it could be root-level in
     any of them. Tag each entry's rel_path with its source root's label so
     every finding in the report says exactly which repo/checkout it came
     from, not just a path that happens to collide across roots. *)
  let all_entries =
    List.concat_map
      (fun root ->
        let label = Filename.basename root in
        Scanner.scan root
        |> List.map (fun (e : Scanner.file_entry) ->
               { e with Scanner.rel_path = Filename.concat label e.rel_path }))
      !roots
  in
  let duplicate_groups = Duplicate_finder.find all_entries in
  let name_clusters = Name_clusterer.cluster all_entries in
  let branch_infos =
    match (!repo_dir, !branches) with
    | Some dir, (_ :: _ as bs) -> Branch_analyzer.analyze ~repo_dir:dir ~base_ref:!base_ref bs
    | _ -> []
  in
  let catalogued = Data_manifest.catalog all_entries in
  let data_duplicate_groups = Data_manifest.duplicates catalogued in

  (* label_to_dir lets an annotation for any file look up ITS OWN repo's git
     history: the label prefixing every rel_path (see all_entries above) is
     exactly the --root's basename, and that --root IS the git checkout, so
     recovering the physical repo directory from a file's label is direct. *)
  let label_to_dir = List.map (fun root -> (Filename.basename root, root)) !roots in
  let rel_path_in_own_repo (f : Scanner.file_entry) =
    let label = Cleanup.repo_label f in
    let prefix_len = String.length label + 1 in
    if String.length f.rel_path > prefix_len then
      String.sub f.rel_path prefix_len (String.length f.rel_path - prefix_len)
    else f.rel_path
  in
  let recency_of (f : Scanner.file_entry) =
    match List.assoc_opt (Cleanup.repo_label f) label_to_dir with
    | Some dir -> Recency.lookup ~repo_dir:dir ~rel_path_in_repo:(rel_path_in_own_repo f)
    | None -> None
  in
  (* Precompute which file is "most recently touched (in its own repo's
     history)" within each duplicate group, so the report can flag it
     directly instead of leaving a human to eyeball a column of dates. *)
  let most_recent_rel_paths =
    let tbl = Hashtbl.create 64 in
    List.iter
      (fun (g : Duplicate_finder.group) ->
        let with_recency = List.map (fun f -> (f, recency_of f)) g.files in
        match Recency.most_recent with_recency with
        | Some (winner : Scanner.file_entry) -> Hashtbl.replace tbl winner.rel_path ()
        | None -> ())
      (duplicate_groups @ data_duplicate_groups);
    tbl
  in
  let human_size n =
    if n >= 1_000_000 then Printf.sprintf "%.1fMB" (float_of_int n /. 1_000_000.)
    else if n >= 1_000 then Printf.sprintf "%.1fKB" (float_of_int n /. 1_000.)
    else Printf.sprintf "%dB" n
  in
  let annotate (f : Scanner.file_entry) =
    let recency_str =
      match recency_of f with
      | Some (info : Recency.info) -> Printf.sprintf "last touched %s" info.last_commit_date
      | None -> "no git history found for this path"
    in
    let winner_marker = if Hashtbl.mem most_recent_rel_paths f.rel_path then " **<- most recently touched**" else "" in
    Some (Printf.sprintf "(%s, %s)%s" (human_size f.size_bytes) recency_str winner_marker)
  in

  (match !data_manifest_out with
  | Some path ->
      let oc = open_out path in
      List.iter
        (fun row -> output_string oc (String.concat "," (List.map (Printf.sprintf "%S") row) ^ "\n"))
        (Data_manifest.to_csv_rows catalogued);
      close_out oc;
      Printf.printf "Wrote %s (%d data file%s cataloged)\n" path (List.length catalogued)
        (if List.length catalogued = 1 then "" else "s")
  | None -> ());

  let report =
    Report.render
      ~root:(String.concat ", " (List.rev !roots))
      ~duplicate_groups ~name_clusters ~branches:branch_infos ~data_duplicate_groups ~annotate ()
  in
  (match !out_path with
  | Some path ->
      let oc = open_out path in
      output_string oc report;
      close_out oc;
      Printf.printf "Wrote %s\n" path
  | None -> print_string report);

  (* data_duplicate_groups is LFS-pointer-only (see Data_manifest.duplicates)
     precisely so it can't re-report what duplicate_groups already found --
     but two independent plans are combined here regardless of that, so
     dedupe defensively by each action's (keep, remove-set) signature rather
     than assume that invariant holds forever. *)
  let dedupe_actions actions =
    let seen = Hashtbl.create 16 in
    List.filter
      (fun (a : Cleanup.action) ->
        let sig_ =
          String.concat "|"
            (a.keep.Scanner.rel_path
            :: List.sort compare (List.map (fun (f : Scanner.file_entry) -> f.Scanner.rel_path) a.remove))
        in
        if Hashtbl.mem seen sig_ then false
        else (
          Hashtbl.add seen sig_ ();
          true))
      actions
  in
  let cleanup_actions = dedupe_actions (Cleanup.plan duplicate_groups @ Cleanup.plan data_duplicate_groups) in
  if cleanup_actions = [] then print_endline "\nNo within-repo exact duplicates to clean up."
  else (
    Printf.printf "\n%s%d within-repo duplicate group(s):\n"
      (if !apply then "Removing " else "Would remove (dry run -- pass --apply to actually delete) ")
      (List.length cleanup_actions);
    List.iter
      (fun (a : Cleanup.action) ->
        Printf.printf "  keep `%s`\n" a.keep.Scanner.rel_path;
        List.iter (fun (f : Scanner.file_entry) -> Printf.printf "    remove `%s`\n" f.Scanner.rel_path) a.remove)
      cleanup_actions;
    let results = Cleanup.apply ~dry_run:(not !apply) cleanup_actions in
    let failures = List.filter (fun (_, err) -> err <> None) results in
    if !apply then
      if failures = [] then Printf.printf "Removed %d file(s).\n" (List.length results)
      else (
        Printf.printf "Removed %d of %d file(s); %d failed:\n" (List.length results - List.length failures)
          (List.length results) (List.length failures);
        List.iter
          (fun ((f : Scanner.file_entry), err) ->
            match err with
            | Some e -> Printf.printf "  `%s`: %s\n" f.rel_path (Printexc.to_string e)
            | None -> ())
          failures))
