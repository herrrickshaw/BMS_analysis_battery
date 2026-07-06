(** Per-file "when was this last touched" lookup, scoped to a single
    repo's own git history -- this is what turns "these two files across
    two repos are byte-identical" into "and here's which repo last
    changed it, so here's the presumptive current copy." Recency, not
    completeness: for an exact-duplicate group the files are byte-for-byte
    identical by definition, so there is no "more complete" one -- only a
    "more recently touched" one. Completeness (size) is a separate,
    independent signal this module doesn't compute; see how it's combined
    with size in the report for differently-sized files (name clusters),
    where both actually vary. *)

type info = {
  last_commit_date : string;  (** ISO 8601 *)
  last_commit_subject : string;
}

val lookup : repo_dir:string -> rel_path_in_repo:string -> info option
(** [lookup ~repo_dir ~rel_path_in_repo] runs `git log -1` inside
    [repo_dir] for the given path (relative to that repo's root, NOT
    including any cross-repo label prefix the CLI may have added).
    Returns [None] if the path has no history in that repo (never
    committed, wrong path, or [repo_dir] isn't a git repo at all) rather
    than raising -- one file's missing history shouldn't abort analysis
    of the rest. *)

val most_recent : (Scanner.file_entry * info option) list -> Scanner.file_entry option
(** Of the files that DO have recency info, returns the one with the
    latest [last_commit_date] (ISO 8601 sorts correctly as a plain string
    comparison). [None] if every file's info lookup failed. *)
