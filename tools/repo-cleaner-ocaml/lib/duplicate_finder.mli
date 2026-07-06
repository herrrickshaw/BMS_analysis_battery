(** Exact-duplicate detection: files that are byte-for-byte identical,
    grouped by content hash. This catches the same file copy-pasted across
    repos (or across directories within one repo) -- it does NOT catch two
    files that implement the same idea differently (a Python script and an
    HTML page computing the same DISCOM formula, say). That kind of
    conceptual duplication needs a human or a language-aware tool; see
    {!Name_clusterer} for the structural (name-based) signal this tool uses
    instead. *)

type group = {
  hash : string;
  size_bytes : int;
  files : Scanner.file_entry list;  (** 2 or more entries, byte-identical *)
}

val find : Scanner.file_entry list -> group list
(** [find entries] hashes every entry and groups them by content hash,
    keeping only groups with 2+ members (an actual duplicate). Empty files
    are excluded -- every empty file trivially "matches" every other empty
    file, which is noise, not redundancy. Sorted by total wasted bytes
    (size * (count - 1)) descending, so the highest-impact duplicates are
    reported first. *)
