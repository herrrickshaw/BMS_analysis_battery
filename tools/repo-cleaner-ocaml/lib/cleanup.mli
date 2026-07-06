(** Turns a subset of duplicate-group findings into an actual removal plan
    -- and only that subset. This module deliberately does NOT try to
    resolve every duplicate group it's given: a cross-repo duplicate means
    "which of these repos is the canonical owner of this file," and that's
    a judgment this tool has no basis to make silently. It only ever plans
    removals within a single repo (all copies share the same leading path
    label, e.g. `main-repo/...` vs `main-repo/...` -- never
    `main-repo/...` vs `fuel-retail-outlets/...`), where "keep exactly one
    copy" has no ownership ambiguity at all. Everything else stays
    report-only, same as {!Name_clusterer} clusters and
    {!Branch_analyzer} branches. *)

type action = {
  keep : Scanner.file_entry;
  remove : Scanner.file_entry list;
}

val repo_label : Scanner.file_entry -> string
(** The leading path component of [rel_path] -- the repo label assigned by
    the CLI when scanning multiple [--root]s. *)

val default_protected_name_fragments : string list
(** [["latest"; "current"; "stable"]] -- a file whose basename contains one
    of these (case-insensitive) is very likely an intentional stable alias
    something else reads from (a fixed path a script or workflow depends
    on), not an accidental duplicate. It being byte-identical to another
    file *today* doesn't mean deleting it is safe: a real run of this tool
    proposed deleting `backtest_1yr_full_NSE_latest.xlsx` and keeping only
    its timestamped twin, purely because "1yr_full_NSE_latest" sorts after
    "Downloads" alphabetically -- exactly the kind of silent breakage this
    guards against. *)

val plan : ?protected_name_fragments:string list -> Duplicate_finder.group list -> action list
(** [plan groups] keeps only groups where every file shares the same
    {!repo_label} AND no file's basename contains one of
    [protected_name_fragments] (default {!default_protected_name_fragments}),
    then proposes keeping the alphabetically-first [rel_path] and removing
    the rest. Cross-repo groups and protected-name groups are silently
    excluded from the plan (they still appear in the report; they're just
    never planned for removal). *)

val apply : dry_run:bool -> action list -> (Scanner.file_entry * exn option) list
(** [apply ~dry_run actions] does nothing when [dry_run] is true (the
    default posture everywhere else in this tool) and otherwise calls
    [Sys.remove] on every [remove] file, returning [(file, None)] on
    success or [(file, Some exn)] if removal failed for that one file
    (permissions, already gone, etc.) -- one failure doesn't abort the
    rest of the plan. *)
