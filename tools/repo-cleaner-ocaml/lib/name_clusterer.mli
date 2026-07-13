(** Groups files whose *names* suggest they're the same document at
    different stages of iteration -- [RESEARCH_PAPER.md] /
    [RESEARCH_PAPER_DETAILED.md] / [RESEARCH_PAPER_SIMPLE.md], or
    [PHASE1_KICKOFF_CHECKLIST.md] / [PHASE_1_KICKOFF.txt] -- even when
    their content differs, which {!Duplicate_finder} can't see.

    This is a naming heuristic, not a content analysis: it flags candidates
    for a human to actually read and decide "supersede, merge, or keep
    both," it does not decide that itself. Expect some over-clustering
    (several unrelated docs that happen to share a generic first word) --
    that's a cheap false positive for a report a human reads, not a
    correctness bug. *)

val normalize_stem : string -> string list
(** [normalize_stem basename] uppercases, strips digits, and splits on
    non-alphanumeric characters, dropping empty tokens. E.g.
    ["PHASE1_KICKOFF.txt"] and ["PHASE_1_kickoff_CHECKLIST.md"] both start
    with the token ["PHASE"]. Exposed directly so tests can pin down the
    normalization rules independently of clustering. *)

type cluster = {
  key : string;  (** the shared leading token *)
  files : Scanner.file_entry list;
}

val cluster : ?min_token_length:int -> Scanner.file_entry list -> cluster list
(** [cluster ?min_token_length entries] groups entries by the first token of
    their normalized basename, keeping only groups of 2+ files whose shared
    token is at least [min_token_length] characters (default 4 -- long
    enough to skip clustering on trivial words). Sorted by cluster size
    descending. *)
