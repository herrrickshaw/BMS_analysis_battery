(* Plain assert + print-OK tests, matching this project's Python test
   convention rather than pulling in an OCaml test framework for a tool
   this small. Each test builds its own throwaway directory/repo under
   the system temp dir and cleans up after itself. *)

open Repo_cleaner_lib

let fresh_dir prefix =
  let base = Filename.temp_file prefix "" in
  Sys.remove base;
  Unix.mkdir base 0o755;
  base

let write_file dir rel_path contents =
  let path = Filename.concat dir rel_path in
  let parent = Filename.dirname path in
  let rec mkdir_p d = if d <> "." && d <> "/" && not (Sys.file_exists d) then (
      mkdir_p (Filename.dirname d);
      Unix.mkdir d 0o755)
  in
  mkdir_p parent;
  let oc = open_out path in
  output_string oc contents;
  close_out oc

let rec rm_rf path =
  if Sys.is_directory path then (
    Array.iter (fun name -> rm_rf (Filename.concat path name)) (Sys.readdir path);
    Unix.rmdir path)
  else Sys.remove path

let run_git dir args =
  let cmd =
    Printf.sprintf "git -C %s %s > /dev/null 2>&1" (Filename.quote dir)
      (String.concat " " (List.map Filename.quote args))
  in
  if Sys.command cmd <> 0 then failwith ("git command failed: " ^ cmd)

(* ---------- Name_clusterer.normalize_stem ---------- *)

let test_normalize_stem_strips_digits_and_splits () =
  assert (Name_clusterer.normalize_stem "PHASE1_KICKOFF.txt" = [ "PHASE"; "KICKOFF" ]);
  assert (Name_clusterer.normalize_stem "PHASE_1_KICKOFF_CHECKLIST.md" = [ "PHASE"; "KICKOFF"; "CHECKLIST" ]);
  assert (Name_clusterer.normalize_stem "ARCHITECTURE.md" = [ "ARCHITECTURE" ]);
  print_endline "OK normalize_stem_strips_digits_and_splits"

(* ---------- Scanner ---------- *)

let test_scanner_finds_files_and_skips_git_dir () =
  let dir = fresh_dir "scanner_test" in
  write_file dir "a.txt" "hello";
  write_file dir "sub/b.txt" "world";
  write_file dir ".git/objects/should_be_skipped" "not a real file";
  let entries = Scanner.scan dir in
  let rel_paths = List.map (fun (e : Scanner.file_entry) -> e.rel_path) entries |> List.sort compare in
  assert (rel_paths = [ "a.txt"; "sub/b.txt" ]);
  rm_rf dir;
  print_endline "OK scanner_finds_files_and_skips_git_dir"

let test_scanner_does_not_follow_symlinks () =
  let dir = fresh_dir "scanner_symlink_test" in
  write_file dir "real.txt" "content";
  Unix.symlink dir (Filename.concat dir "loop");
  (* a symlink to its own parent -- if the scanner followed it, this would
     recurse forever *)
  let entries = Scanner.scan dir in
  let rel_paths = List.map (fun (e : Scanner.file_entry) -> e.rel_path) entries in
  assert (rel_paths = [ "real.txt" ]);
  Sys.remove (Filename.concat dir "loop");
  rm_rf dir;
  print_endline "OK scanner_does_not_follow_symlinks"

let test_scanner_skips_build_and_dependency_dirs_by_default () =
  (* Regression test: a real run of this tool against its own checked-out
     source found _build/ (dune's output, a byte-identical copy of every
     source file) sorting alphabetically BEFORE lib/, which would have
     made Cleanup.plan propose keeping the build artifact and deleting the
     real source. Caught in a dry run before anything was removed; this
     pins the actual fix down so it can't regress silently. *)
  let dir = fresh_dir "scanner_buildartifact_test" in
  write_file dir "lib/scanner.ml" "real source";
  write_file dir "_build/default/lib/scanner.ml" "real source";
  write_file dir "node_modules/pkg/index.js" "vendored";
  write_file dir "__pycache__/mod.pyc" "bytecode";
  let entries = Scanner.scan dir in
  let rel_paths = List.map (fun (e : Scanner.file_entry) -> e.rel_path) entries |> List.sort compare in
  assert (rel_paths = [ "lib/scanner.ml" ]);
  rm_rf dir;
  print_endline "OK scanner_skips_build_and_dependency_dirs_by_default"

(* ---------- Duplicate_finder ---------- *)

let test_duplicate_finder_finds_byte_identical_across_dirs () =
  let dir = fresh_dir "dupe_test" in
  write_file dir "repoA/api-data-integration/loader.py" "SAME CONTENT\n";
  write_file dir "repoB/api-data-integration/loader.py" "SAME CONTENT\n";
  write_file dir "repoC/unrelated.py" "different content entirely\n";
  let entries = Scanner.scan dir in
  let groups = Duplicate_finder.find entries in
  assert (List.length groups = 1);
  let g = List.hd groups in
  assert (List.length g.files = 2);
  assert (g.size_bytes = String.length "SAME CONTENT\n");
  rm_rf dir;
  print_endline "OK duplicate_finder_finds_byte_identical_across_dirs"

let test_duplicate_finder_ignores_empty_files () =
  let dir = fresh_dir "dupe_empty_test" in
  write_file dir "a/__init__.py" "";
  write_file dir "b/__init__.py" "";
  let entries = Scanner.scan dir in
  let groups = Duplicate_finder.find entries in
  assert (groups = []);
  rm_rf dir;
  print_endline "OK duplicate_finder_ignores_empty_files"

(* ---------- Name_clusterer.cluster ---------- *)

let test_name_clusterer_clusters_research_paper_variants () =
  let dir = fresh_dir "cluster_test" in
  write_file dir "RESEARCH_PAPER.md" "v1";
  write_file dir "RESEARCH_PAPER_DETAILED.md" "v2";
  write_file dir "RESEARCH_PAPER_SIMPLE.md" "v3";
  write_file dir "OTHER.md" "unrelated";
  let entries = Scanner.scan dir in
  let clusters = Name_clusterer.cluster entries in
  assert (List.length clusters = 1);
  let c = List.hd clusters in
  assert (c.key = "RESEARCH");
  assert (List.length c.files = 3);
  rm_rf dir;
  print_endline "OK name_clusterer_clusters_research_paper_variants"

let test_name_clusterer_respects_min_token_length () =
  let dir = fresh_dir "cluster_short_test" in
  write_file dir "AB_ONE.md" "x";
  write_file dir "AB_TWO.md" "y";
  let entries = Scanner.scan dir in
  let clusters = Name_clusterer.cluster ~min_token_length:4 entries in
  assert (clusters = []);
  rm_rf dir;
  print_endline "OK name_clusterer_respects_min_token_length"

(* ---------- Branch_analyzer ---------- *)

let test_branch_analyzer_computes_ahead_behind_and_classifies () =
  let dir = fresh_dir "branch_test" in
  run_git dir [ "init"; "-q"; "-b"; "main" ];
  run_git dir [ "config"; "user.email"; "test@example.com" ];
  run_git dir [ "config"; "user.name"; "Test" ];
  write_file dir "f.txt" "1";
  run_git dir [ "add"; "f.txt" ];
  run_git dir [ "commit"; "-q"; "-m"; "c1" ];

  (* merged: branched off main, no new commits, main doesn't move -- ahead=0 behind=0 *)
  run_git dir [ "branch"; "merged-branch" ];

  (* recent: one commit ahead, main unmoved since -- behind=0 *)
  run_git dir [ "checkout"; "-q"; "-b"; "recent-branch" ];
  write_file dir "g.txt" "2";
  run_git dir [ "add"; "g.txt" ];
  run_git dir [ "commit"; "-q"; "-m"; "c2" ];
  run_git dir [ "checkout"; "-q"; "main" ];

  let infos =
    Branch_analyzer.analyze ~repo_dir:dir ~base_ref:"main"
      [ "merged-branch"; "recent-branch"; "no-such-branch" ]
  in
  assert (List.length infos = 2);
  (* no-such-branch silently skipped, not raised *)
  let merged = List.find (fun (b : Branch_analyzer.branch_info) -> b.name = "merged-branch") infos in
  let recent = List.find (fun (b : Branch_analyzer.branch_info) -> b.name = "recent-branch") infos in
  assert (merged.ahead = 0 && merged.behind = 0);
  assert (Branch_analyzer.classify merged = `Merged);
  assert (recent.ahead = 1 && recent.behind = 0);
  assert (Branch_analyzer.classify recent = `Recent);
  assert (recent.last_commit_subject = "c2");
  rm_rf dir;
  print_endline "OK branch_analyzer_computes_ahead_behind_and_classifies"

(* ---------- Recency ---------- *)

let make_git_entry_at dir ~rel_path ~content ~subject =
  write_file dir rel_path content;
  run_git dir [ "add"; rel_path ];
  run_git dir [ "commit"; "-q"; "-m"; subject ]

let test_recency_lookup_returns_last_commit_for_path () =
  let dir = fresh_dir "recency_test" in
  run_git dir [ "init"; "-q"; "-b"; "main" ];
  run_git dir [ "config"; "user.email"; "test@example.com" ];
  run_git dir [ "config"; "user.name"; "Test" ];
  make_git_entry_at dir ~rel_path:"a.py" ~content:"v1" ~subject:"add a.py";
  make_git_entry_at dir ~rel_path:"a.py" ~content:"v2" ~subject:"update a.py again";
  match Recency.lookup ~repo_dir:dir ~rel_path_in_repo:"a.py" with
  | Some info ->
      assert (info.Recency.last_commit_subject = "update a.py again");
      rm_rf dir;
      print_endline "OK recency_lookup_returns_last_commit_for_path"
  | None -> failwith "expected recency info for a committed path"

let test_recency_lookup_returns_none_for_unknown_path () =
  let dir = fresh_dir "recency_unknown_test" in
  run_git dir [ "init"; "-q"; "-b"; "main" ];
  run_git dir [ "config"; "user.email"; "test@example.com" ];
  run_git dir [ "config"; "user.name"; "Test" ];
  make_git_entry_at dir ~rel_path:"a.py" ~content:"v1" ~subject:"add a.py";
  assert (Recency.lookup ~repo_dir:dir ~rel_path_in_repo:"never_committed.py" = None);
  rm_rf dir;
  print_endline "OK recency_lookup_returns_none_for_unknown_path"

let test_recency_most_recent_picks_latest_date () =
  let mk rel_path date_str =
    ({ Scanner.abs_path = rel_path; rel_path; size_bytes = 0 }, Some { Recency.last_commit_date = date_str; last_commit_subject = "" })
  in
  let entries =
    [
      mk "repoA/x.py" "2025-01-01T00:00:00+00:00";
      mk "repoB/x.py" "2026-06-15T00:00:00+00:00";
      mk "repoC/x.py" "2024-11-30T00:00:00+00:00";
    ]
  in
  match Recency.most_recent entries with
  | Some f -> assert (f.Scanner.rel_path = "repoB/x.py");
      print_endline "OK recency_most_recent_picks_latest_date"
  | None -> failwith "expected a most-recent file"

let test_recency_most_recent_returns_none_when_nothing_resolved () =
  let entries = [ ({ Scanner.abs_path = "x"; rel_path = "x"; size_bytes = 0 }, None) ] in
  assert (Recency.most_recent entries = None);
  print_endline "OK recency_most_recent_returns_none_when_nothing_resolved"

(* ---------- Data_manifest ---------- *)

let lfs_pointer_text oid size =
  Printf.sprintf "version https://git-lfs.github.com/spec/v1\noid sha256:%s\nsize %d\n" oid size

let test_parse_lfs_pointer_extracts_oid_and_size () =
  let oid = String.make 64 'a' in
  let text = lfs_pointer_text oid 12345678 in
  match Data_manifest.parse_lfs_pointer text with
  | Some (parsed_oid, parsed_size) ->
      assert (parsed_oid = oid);
      assert (parsed_size = 12345678);
      print_endline "OK parse_lfs_pointer_extracts_oid_and_size"
  | None -> failwith "expected a parsed pointer"

let test_parse_lfs_pointer_rejects_real_content () =
  assert (Data_manifest.parse_lfs_pointer "PK\x03\x04 binary parquet bytes, not a pointer" = None);
  assert (Data_manifest.parse_lfs_pointer "" = None);
  print_endline "OK parse_lfs_pointer_rejects_real_content"

let test_catalog_reports_true_size_from_pointer_not_ondisk_size () =
  let dir = fresh_dir "manifest_test" in
  let oid = String.make 64 'b' in
  (* the pointer FILE on disk is tiny; the dataset it stands in for is declared as 50MB *)
  write_file dir "data/big_cache.parquet" (lfs_pointer_text oid 50_000_000);
  let entries = Scanner.scan dir in
  let catalogued = Data_manifest.catalog entries in
  assert (List.length catalogued = 1);
  let c = List.hd catalogued in
  assert c.is_lfs_pointer;
  assert (c.true_size_bytes = 50_000_000);
  assert (c.true_size_bytes <> c.file.Scanner.size_bytes);
  (* the pointer text itself is well under 200 bytes *)
  assert (c.content_key = Some ("lfs:" ^ oid));
  rm_rf dir;
  print_endline "OK catalog_reports_true_size_from_pointer_not_ondisk_size"

let test_catalog_ignores_non_data_extensions () =
  let dir = fresh_dir "manifest_ext_test" in
  write_file dir "notes.txt" "not a data file";
  write_file dir "data.csv" "a,b,c\n1,2,3\n";
  let entries = Scanner.scan dir in
  let catalogued = Data_manifest.catalog entries in
  assert (List.length catalogued = 1);
  assert ((List.hd catalogued).file.Scanner.rel_path = "data.csv");
  rm_rf dir;
  print_endline "OK catalog_ignores_non_data_extensions"

let test_data_manifest_duplicates_finds_same_lfs_oid_across_repos () =
  let dir = fresh_dir "manifest_dupe_test" in
  let shared_oid = String.make 64 'c' in
  write_file dir "repoA/cache_seed/US.parquet" (lfs_pointer_text shared_oid 900_000);
  write_file dir "repoB/cache_seed/US.parquet" (lfs_pointer_text shared_oid 900_000);
  write_file dir "repoC/cache_seed/IN.parquet"
    (lfs_pointer_text (String.make 64 'd') 500_000);
  let entries = Scanner.scan dir in
  let catalogued = Data_manifest.catalog entries in
  let groups = Data_manifest.duplicates catalogued in
  assert (List.length groups = 1);
  let g = List.hd groups in
  assert (List.length g.Duplicate_finder.files = 2);
  assert (g.Duplicate_finder.size_bytes = 900_000);
  rm_rf dir;
  print_endline "OK data_manifest_duplicates_finds_same_lfs_oid_across_repos"

let test_to_csv_rows_has_header_and_one_row_per_entry () =
  let dir = fresh_dir "manifest_csv_test" in
  write_file dir "a.json" "{}";
  write_file dir "b.parquet" (lfs_pointer_text (String.make 64 'e') 42);
  let catalogued = Data_manifest.catalog (Scanner.scan dir) in
  let rows = Data_manifest.to_csv_rows catalogued in
  assert (List.length rows = 3);
  (* header + 2 entries *)
  assert (List.hd rows = [ "path"; "kind"; "true_size_bytes"; "is_lfs_pointer"; "content_key" ]);
  rm_rf dir;
  print_endline "OK to_csv_rows_has_header_and_one_row_per_entry"

(* ---------- Cleanup ---------- *)

let test_cleanup_plans_within_repo_duplicates () =
  let dir = fresh_dir "cleanup_test" in
  write_file dir "repoA/notification.html" "same content";
  write_file dir "repoA/notification (1).html" "same content";
  (* rel_path already starts with "repoA/" here since that's the directory
     structure under the scan root -- this mirrors what the CLI produces by
     prefixing each --root's entries with its own repo label. *)
  let groups = Duplicate_finder.find (Scanner.scan dir) in
  let actions = Cleanup.plan groups in
  assert (List.length actions = 1);
  let a = List.hd actions in
  assert (a.Cleanup.keep.Scanner.rel_path = "repoA/notification (1).html");
  (* alphabetically first: '(' < 'n' as raw bytes -- pin the actual rule down, not just "some file" *)
  assert (List.length a.Cleanup.remove = 1);
  rm_rf dir;
  print_endline "OK cleanup_plans_within_repo_duplicates"

let test_cleanup_skips_groups_with_a_protected_alias_name () =
  (* Regression test: a real run proposed deleting a "_latest" file and
     keeping only its timestamped twin, purely on alphabetical sort order
     -- exactly the kind of silent breakage a stable-alias filename should
     block, even though the two files are genuinely byte-identical. *)
  let dir = fresh_dir "cleanup_latest_test" in
  write_file dir "repoA/scan_results/backtest_1yr_full_NSE_latest.xlsx" "same bytes";
  write_file dir "repoA/Downloads/data/backtest_results/backtest_IN_20260626_1300.xlsx" "same bytes";
  let groups = Duplicate_finder.find (Scanner.scan dir) in
  let actions = Cleanup.plan groups in
  assert (actions = []);
  rm_rf dir;
  print_endline "OK cleanup_skips_groups_with_a_protected_alias_name"

let test_cleanup_skips_cross_repo_duplicates () =
  let dir = fresh_dir "cleanup_cross_test" in
  write_file dir "repoA/shared_script.py" "identical logic";
  write_file dir "repoB/shared_script.py" "identical logic";
  let entries = Scanner.scan dir in
  let groups = Duplicate_finder.find entries in
  let actions = Cleanup.plan groups in
  assert (actions = []);
  rm_rf dir;
  print_endline "OK cleanup_skips_cross_repo_duplicates"

let test_cleanup_apply_dry_run_removes_nothing () =
  let dir = fresh_dir "cleanup_dryrun_test" in
  write_file dir "repoA/a.txt" "dup";
  write_file dir "repoA/b.txt" "dup";
  let groups = Duplicate_finder.find (Scanner.scan dir) in
  let actions = Cleanup.plan groups in
  let results = Cleanup.apply ~dry_run:true actions in
  assert (results = []);
  assert (Sys.file_exists (Filename.concat dir "repoA/a.txt"));
  assert (Sys.file_exists (Filename.concat dir "repoA/b.txt"));
  rm_rf dir;
  print_endline "OK cleanup_apply_dry_run_removes_nothing"

let test_cleanup_apply_real_run_removes_all_but_kept () =
  let dir = fresh_dir "cleanup_apply_test" in
  write_file dir "repoA/a.txt" "dup";
  write_file dir "repoA/b.txt" "dup";
  write_file dir "repoA/c.txt" "dup";
  let groups = Duplicate_finder.find (Scanner.scan dir) in
  let actions = Cleanup.plan groups in
  let results = Cleanup.apply ~dry_run:false actions in
  assert (List.length results = 2);
  assert (List.for_all (fun (_, err) -> err = None) results);
  assert (Sys.file_exists (Filename.concat dir "repoA/a.txt"));
  assert (not (Sys.file_exists (Filename.concat dir "repoA/b.txt")));
  assert (not (Sys.file_exists (Filename.concat dir "repoA/c.txt")));
  rm_rf dir;
  print_endline "OK cleanup_apply_real_run_removes_all_but_kept"

(* ---------- Report ---------- *)

let contains hay needle =
  let hl = String.length hay and nl = String.length needle in
  let rec go i = i + nl <= hl && (String.sub hay i nl = needle || go (i + 1)) in
  go 0

let test_report_render_includes_all_sections () =
  let out = Report.render ~root:"/tmp/example" ~duplicate_groups:[] ~name_clusters:[] ~branches:[] () in
  assert (contains out "repo-cleaner-ocaml report");
  assert (contains out "Exact duplicate files");
  assert (contains out "Name-based doc-sprawl clusters");
  assert (contains out "Branch staleness vs base");
  print_endline "OK report_render_includes_all_sections"

let () =
  test_normalize_stem_strips_digits_and_splits ();
  test_scanner_finds_files_and_skips_git_dir ();
  test_scanner_does_not_follow_symlinks ();
  test_scanner_skips_build_and_dependency_dirs_by_default ();
  test_duplicate_finder_finds_byte_identical_across_dirs ();
  test_duplicate_finder_ignores_empty_files ();
  test_name_clusterer_clusters_research_paper_variants ();
  test_name_clusterer_respects_min_token_length ();
  test_branch_analyzer_computes_ahead_behind_and_classifies ();
  test_recency_lookup_returns_last_commit_for_path ();
  test_recency_lookup_returns_none_for_unknown_path ();
  test_recency_most_recent_picks_latest_date ();
  test_recency_most_recent_returns_none_when_nothing_resolved ();
  test_parse_lfs_pointer_extracts_oid_and_size ();
  test_parse_lfs_pointer_rejects_real_content ();
  test_catalog_reports_true_size_from_pointer_not_ondisk_size ();
  test_catalog_ignores_non_data_extensions ();
  test_data_manifest_duplicates_finds_same_lfs_oid_across_repos ();
  test_to_csv_rows_has_header_and_one_row_per_entry ();
  test_cleanup_plans_within_repo_duplicates ();
  test_cleanup_skips_groups_with_a_protected_alias_name ();
  test_cleanup_skips_cross_repo_duplicates ();
  test_cleanup_apply_dry_run_removes_nothing ();
  test_cleanup_apply_real_run_removes_all_but_kept ();
  test_report_render_includes_all_sections ();
  print_endline "\nAll repo-cleaner-ocaml tests passed."
