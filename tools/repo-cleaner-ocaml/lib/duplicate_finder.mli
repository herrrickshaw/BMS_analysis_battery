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

val group_by_key :
  key_of:(Scanner.file_entry -> string option) ->
  size_of:(Scanner.file_entry -> int) ->
  Scanner.file_entry list ->
  group list
(** The general form [find] is built on: group entries by whatever
    [key_of] returns (skipping entries where it returns [None]), keeping
    only groups of 2+, with [size_of] driving the reported/waste size
    instead of always [Scanner.file_entry.size_bytes]. Used by
    {!Data_manifest} to group by LFS pointer [oid] instead of a raw
    content hash -- the same duplicate-detection shape, a different
    notion of "identical." *)
