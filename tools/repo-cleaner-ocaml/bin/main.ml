open Repo_cleaner_lib

let roots = ref []
let repo_dir = ref None
let base_ref = ref "main"
let branches = ref []
let out_path = ref None

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
  ]

let usage =
  "repo_cleaner --root <dir> [--root <dir> ...] [--repo-dir <dir> --branch <name> ...] [--out report.md]\n\n\
   Structural redundancy report only: exact-duplicate files, name-based doc-sprawl\n\
   clusters, and branch staleness vs a base ref. Never deletes anything -- every\n\
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

  let report =
    Report.render
      ~root:(String.concat ", " (List.rev !roots))
      ~duplicate_groups ~name_clusters ~branches:branch_infos
  in
  match !out_path with
  | Some path ->
      let oc = open_out path in
      output_string oc report;
      close_out oc;
      Printf.printf "Wrote %s\n" path
  | None -> print_string report
