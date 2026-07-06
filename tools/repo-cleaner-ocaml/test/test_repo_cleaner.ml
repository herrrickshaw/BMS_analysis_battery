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
  let cmd = Printf.sprintf "git -C %s %s > /dev/null 2>&1" (Filename.quote dir) (String.concat " " args) in
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

(* ---------- Report ---------- *)

let contains hay needle =
  let hl = String.length hay and nl = String.length needle in
  let rec go i = i + nl <= hl && (String.sub hay i nl = needle || go (i + 1)) in
  go 0

let test_report_render_includes_all_sections () =
  let out = Report.render ~root:"/tmp/example" ~duplicate_groups:[] ~name_clusters:[] ~branches:[] in
  assert (contains out "repo-cleaner-ocaml report");
  assert (contains out "Exact duplicate files");
  assert (contains out "Name-based doc-sprawl clusters");
  assert (contains out "Branch staleness vs base");
  print_endline "OK report_render_includes_all_sections"

let () =
  test_normalize_stem_strips_digits_and_splits ();
  test_scanner_finds_files_and_skips_git_dir ();
  test_scanner_does_not_follow_symlinks ();
  test_duplicate_finder_finds_byte_identical_across_dirs ();
  test_duplicate_finder_ignores_empty_files ();
  test_name_clusterer_clusters_research_paper_variants ();
  test_name_clusterer_respects_min_token_length ();
  test_branch_analyzer_computes_ahead_behind_and_classifies ();
  test_report_render_includes_all_sections ();
  print_endline "\nAll repo-cleaner-ocaml tests passed."
