let human_bytes n =
  if n >= 1_000_000 then Printf.sprintf "%.1fMB" (float_of_int n /. 1_000_000.)
  else if n >= 1_000 then Printf.sprintf "%.1fKB" (float_of_int n /. 1_000.)
  else Printf.sprintf "%dB" n

let render ~root ~duplicate_groups ~name_clusters ~branches =
  let buf = Buffer.create 4096 in
  let p fmt = Printf.ksprintf (fun s -> Buffer.add_string buf s; Buffer.add_char buf '\n') fmt in

  p "# repo-cleaner-ocaml report";
  p "";
  p "Scanned root: `%s`" root;
  p "";
  p "This report only lists candidates. Nothing here has been deleted --";
  p "every finding below needs a human decision before anything is removed.";
  p "";

  p "## Exact duplicate files (%d group%s)" (List.length duplicate_groups)
    (if List.length duplicate_groups = 1 then "" else "s");
  p "";
  if duplicate_groups = [] then p "None found."
  else
    List.iter
      (fun (g : Duplicate_finder.group) ->
        let waste = g.size_bytes * (List.length g.files - 1) in
        p "- **%s wasted** (%d copies of a %s file):" (human_bytes waste) (List.length g.files)
          (human_bytes g.size_bytes);
        List.iter (fun (f : Scanner.file_entry) -> p "  - `%s`" f.rel_path) g.files)
      duplicate_groups;
  p "";

  p "## Name-based doc-sprawl clusters (%d cluster%s)" (List.length name_clusters)
    (if List.length name_clusters = 1 then "" else "s");
  p "";
  p "Files sharing a leading name token -- candidates for a human to read and";
  p "decide \"supersede, merge, or keep both.\" Over-inclusion is expected; this";
  p "is a naming heuristic, not a content judgment.";
  p "";
  if name_clusters = [] then p "None found."
  else
    List.iter
      (fun (c : Name_clusterer.cluster) ->
        p "- **%s** (%d files):" c.key (List.length c.files);
        List.iter (fun (f : Scanner.file_entry) -> p "  - `%s`" f.rel_path) c.files)
      name_clusters;
  p "";

  p "## Branch staleness vs base";
  p "";
  if branches = [] then p "None found."
  else (
    p "| Branch | Ahead | Behind | Last commit | Triage |";
    p "|---|---:|---:|---|---|";
    List.iter
      (fun (b : Branch_analyzer.branch_info) ->
        let label =
          match Branch_analyzer.classify b with
          | `Merged -> "merged -- nothing unique, safe to delete"
          | `Likely_stale -> "likely stale -- review before deleting"
          | `Recent -> "recent -- review for a real merge decision"
        in
        p "| `%s` | %d | %d | %s | %s |" b.name b.ahead b.behind
          (if b.last_commit_date = "" then "(unknown)" else b.last_commit_date)
          label)
      branches);
  p "";
  Buffer.contents buf
